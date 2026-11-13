#include "kateeditor.h"

#include "katehost.h"

#include <KTextEditor/ConfigPage>
#include <KTextEditor/Document>
#include <KTextEditor/Editor>
#include <KTextEditor/MainWindow>
#include <KTextEditor/View>
#include <ktexteditor_version.h>

#include <KActionCollection>
#include <KLocalizedString>
#include <KPageDialog>

#include <QAction>
#include <QApplication>
#include <QDialogButtonBox>
#include <QEvent>
#include <QFileInfo>
#include <QFocusEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QFontMetrics>
#include <QKeySequence>
#include <QPushButton>
#include <QQuickWindow>
#include <QTimer>
#include <QStackedLayout>
#include <QWidget>
#include <QWindow>

#include <memory>

KateEditor::KateEditor(QQuickItem *parent)
    : NativeWidgetItem(parent)
{
    // QWidgets need a QApplication (Kreator has one)
    if (!qobject_cast<QApplication *>(QCoreApplication::instance())) {
        qWarning("KateEditor: needs a QApplication");
        return;
    }
    // the item holds QML's focus while Kate has the keyboard, so no QML field
    // looks (or is) focused at the same time
    setFlag(ItemIsFocusScope, false);
    setActiveFocusOnTab(true);
    setFlag(ItemAcceptsInputMethod, true);
    // Kreator as Kate's main window; this also brings Kate's settings
    KateHost *host = KateHost::instance();
    // the tabs' views, one shown at a time, in one native widget
    m_container = new QWidget;
    m_stack = new QStackedLayout(m_container);
    m_stack->setContentsMargins(0, 0, 0, 0);
    setWidget(m_container);
    // a blank document until the first of Kreator's is shown (it takes this one)
    m_entries.insert(QString(), createEntry());
    showEntry(m_entries.value(QString()));
    // Wayland moves focus between surfaces; Qt then resets the active widget
    // window, which would turn Kate's editing keys off again
    connect(qGuiApp, &QGuiApplication::focusWindowChanged, this, [this](QWindow *) {
        if (m_wantsInput)
            QTimer::singleShot(0, this, [this] {
                if (m_wantsInput)
                    activateEditor();
            });
    });

    connect(host, &KateHost::openRequested, this, [this](const QString &path) {
        if (KateHost::instance()->activeView() == m_view)
            Q_EMIT openFileRequested(path);
    });
    connect(host, &KateHost::fileEdited, this, [this](const QString &path, const QString &basis, const QString &text) {
        if (KateHost::instance()->activeView() == m_view)
            Q_EMIT fileEditRequested(path, basis, text);
    });
    connect(host, &KateHost::message, this, &KateEditor::message);
    connect(host, &KateHost::actionsChanged, this, &KateEditor::applyActionRules);
}

KateEditor::~KateEditor()
{
    detachWidget();
    for (auto it = m_entries.begin(); it != m_entries.end(); ++it)
        dropEntry(it.value());
    m_entries.clear();
    delete m_container;
}

KateEditor::Entry KateEditor::createEntry()
{
    KateHost *host = KateHost::instance();
    Entry e;
    e.doc = KTextEditor::Editor::instance()->createDocument(this);
    // Kreator saves its files and notices changes on disk itself
    e.doc->setModifiedOnDiskWarning(false);
    e.view = e.doc->createView(m_container, host->mainWindow());
    m_stack->addWidget(e.view);
    // the context menu comes from the main window's XMLGUI (with the plugins'
    // entries); without one, use the view's default menu
    if (!e.view->contextMenu())
        e.view->setContextMenu(e.view->defaultContextMenu());
    // the widget that takes the keyboard and holds the editing actions
    e.internal = e.view->focusProxy();
    if (!e.internal) {
        const auto kids = e.view->findChildren<QWidget *>();
        for (QWidget *w : kids) {
            if (qstrcmp(w->metaObject()->className(), "KateViewInternal") == 0) {
                e.internal = w;
                break;
            }
        }
    }
    host->addView(e.view);
    // (the shown one's only)
    KTextEditor::Document *doc = e.doc;
    KTextEditor::View *view = e.view;
    connect(doc, &KTextEditor::Document::textChanged, this, [this, doc] {
        if (doc != m_doc)
            return;
        Q_EMIT textChanged();
        if (!m_settingText)
            Q_EMIT textEdited();
    });
    connect(view, &KTextEditor::View::cursorPositionChanged, this, [this, view] {
        if (view == m_view)
            Q_EMIT cursorPositionChanged();
    });
    connect(view, &KTextEditor::View::focusIn, this, [this, view] {
        if (view != m_view)
            return;
        m_focus = true;
        KateHost::instance()->activateView(m_view);
        Q_EMIT editorFocusChanged();
    });
    connect(view, &KTextEditor::View::focusOut, this, [this, view] {
        if (view != m_view)
            return;
        m_focus = false;
        Q_EMIT editorFocusChanged();
    });
    return e;
}

void KateEditor::showEntry(const Entry &entry)
{
    const bool hadInput = m_wantsInput;
    m_doc = entry.doc;
    m_view = entry.view;
    m_internal = entry.internal;
    m_mode = entry.mode;
    // (the views are stacked in one native widget: swapping native windows
    // for every tab switch would take far longer)
    m_stack->setCurrentWidget(m_view);
    KateHost::instance()->activateView(m_view);
    // the keyboard stays with the editor
    if (hadInput)
        activateEditor();
}

void KateEditor::dropEntry(Entry &entry)
{
    if (entry.view) {
        KateHost::instance()->removeView(entry.view);
        m_stack->removeWidget(entry.view);
        delete entry.view;
    }
    if (entry.doc) {
        // no "save changes?" from Kate: Kreator has the changes
        entry.doc->setModified(false);
        delete entry.doc;
    }
    entry = Entry();
}

bool KateEditor::isKateAction(QAction *a) const
{
    if (!a)
        return false;
    if ((m_internal && m_internal->actions().contains(a)) || (m_view && m_view->actions().contains(a)) || isUnderWidget(a))
        return true;
    return KateHost::instance()->pluginActions().contains(a);
}

bool KateEditor::eventFilter(QObject *watched, QEvent *event)
{
    switch (event->type()) {
    case QEvent::ShortcutOverride:
        // a key for this item: note whether Qt's shortcut map fires a Kate
        // action for it before the key press arrives (it does when the view is
        // active)
        if (watched == this)
            m_shortcutFired = false;
        break;
    case QEvent::Shortcut:
        if (isKateAction(qobject_cast<QAction *>(watched)))
            m_shortcutFired = true;
        break;
    case QEvent::KeyPress:
        // Kate's shortcut keys: Qt's shortcut map skips them outside the active
        // window, so they arrive here as plain key presses
        if (watched->isWidgetType() && isUnderWidget(watched))
            return dispatchShortcut(static_cast<QWidget *>(watched), static_cast<QKeyEvent *>(event));
        break;
    case QEvent::MouseButtonPress:
        // who gets the keyboard: a click into the editor, or into Kreator's QML
        if (m_view && watched->isWidgetType() && isUnderWidget(watched))
            activateEditor();
        break;
    case QEvent::MouseButtonRelease:
        // Ctrl+click: Kate's LSP client goes to the definition
        if (m_view && watched == m_internal) {
            auto *me = static_cast<QMouseEvent *>(event);
            if (me->button() == Qt::LeftButton && (me->modifiers() & Qt::ControlModifier)) {
                const QPoint p = m_internal->mapTo(static_cast<QWidget *>(m_view.data()), me->position().toPoint());
                const KTextEditor::Cursor c = m_view->coordinatesToCursor(p);
                if (c.isValid())
                    Q_EMIT definitionRequested(c.line(), c.column());
            }
        }
        break;
    case QEvent::FocusIn:
        // Kreator's window back: the editor keeps its claim
        if (watched == quickWindow() && m_view && m_wantsInput)
            activateEditor();
        break;
    default:
        break;
    }
    return NativeWidgetItem::eventFilter(watched, event);
}

// ------------------------------------------------------------ the document

QString KateEditor::text() const
{
    return m_doc ? m_doc->text() : QString();
}

void KateEditor::setText(const QString &text)
{
    if (!m_doc)
        return;
    if (text != m_doc->text()) {
        m_settingText = true;
        // keep the cursor where it was, as far as possible
        const auto cursor = m_view ? m_view->cursorPosition() : KTextEditor::Cursor();
        m_doc->setText(text);
        if (m_view)
            m_view->setCursorPosition(cursor);
        m_settingText = false;
    }
    // a new document: Kate's undo must not go back to before Kreator's text
    if (m_freshDocument) {
        m_freshDocument = false;
        clearUndo();
        if (auto it = m_entries.find(m_documentKey); it != m_entries.end())
            it->fresh = false;
    }
}

void KateEditor::clearUndo()
{
    // (KTextEditor has no public API for it; its undo manager has slots)
    if (!m_doc)
        return;
    const auto children = m_doc->findChildren<QObject *>(Qt::FindDirectChildrenOnly);
    for (QObject *c : children) {
        if (qstrcmp(c->metaObject()->className(), "KateUndoManager") == 0) {
            QMetaObject::invokeMethod(c, "clearUndo");
            QMetaObject::invokeMethod(c, "clearRedo");
            return;
        }
    }
}

QString KateEditor::mode() const
{
    return m_doc ? m_doc->highlightingMode() : QString();
}

void KateEditor::setMode(const QString &mode)
{
    if (!m_doc || mode == m_mode)
        return;
    m_mode = mode;
    if (auto it = m_entries.find(m_documentKey); it != m_entries.end())
        it->mode = mode;
    m_doc->setHighlightingMode(mode);
    m_doc->setMode(mode);
    Q_EMIT modeChanged();
}

QString KateEditor::fileName() const
{
    return m_fileName;
}

void KateEditor::setFileName(const QString &name)
{
    const bool changed = name != m_fileName;
    m_fileName = name;
    bindUrl();   // (nothing to do when the shown document has it already)
    if (changed)
        Q_EMIT fileNameChanged();
}

QString KateEditor::documentKey() const
{
    return m_documentKey;
}

void KateEditor::setDocumentKey(const QString &key)
{
    if (key == m_documentKey)
        return;
    if (!m_doc) {
        m_documentKey = key;
        Q_EMIT documentKeyChanged();
        return;
    }
    auto it = m_entries.find(key);
    if (it == m_entries.end()) {
        // the blank first document is taken by the first of Kreator's
        auto blank = m_entries.find(QString());
        if (m_documentKey.isEmpty() && blank != m_entries.end() && blank->fresh) {
            const Entry e = *blank;
            m_entries.erase(blank);
            it = m_entries.insert(key, e);
        } else {
            it = m_entries.insert(key, createEntry());
        }
    }
    const bool created = !m_watchedViews.contains(it->view);
    m_reused = !it->fresh;
    m_freshDocument = it->fresh;
    m_documentKey = key;
    showEntry(*it);
    if (created) {   // a new view's own actions get Kreator's key rules
        m_watchedViews.append(it->view);
        applyActionRules();
    }
    Q_EMIT documentKeyChanged();
    Q_EMIT textChanged();
    Q_EMIT modeChanged();
    Q_EMIT cursorPositionChanged();
}

QStringList KateEditor::openKeys() const
{
    return m_openKeys;
}

void KateEditor::setOpenKeys(const QStringList &keys)
{
    if (keys == m_openKeys)
        return;
    m_openKeys = keys;
    for (auto it = m_entries.begin(); it != m_entries.end();) {
        if (it.key() != m_documentKey && !keys.contains(it.key())) {
            dropEntry(it.value());
            it = m_entries.erase(it);
        } else {
            ++it;
        }
    }
    Q_EMIT openKeysChanged();
}

bool KateEditor::documentReused() const
{
    return m_reused;
}

void KateEditor::bindUrl()
{
    // The language server knows documents by URL: the document is opened from
    // the file, then shows Kreator's text (set right after, see setText)
    if (!m_doc)
        return;
    const QFileInfo info(m_fileName);
    const QUrl target = !m_fileName.isEmpty() && info.isFile() ? QUrl::fromLocalFile(info.absoluteFilePath()) : QUrl();
    if (m_doc->url() == target)
        return;
    m_settingText = true;
    // no "save changes?" from Kate: Kreator has the changes
    m_doc->setModified(false);
    if (target.isEmpty())
        m_doc->closeUrl();
    else
        m_doc->openUrl(target);
    m_doc->setModifiedOnDiskWarning(false);
    if (!m_mode.isEmpty()) {
        m_doc->setHighlightingMode(m_mode);
        m_doc->setMode(m_mode);
    }
    m_settingText = false;
    m_freshDocument = true;
    Q_EMIT textChanged();
}

int KateEditor::cursorLine() const
{
    return m_view ? m_view->cursorPosition().line() : 0;
}

int KateEditor::cursorColumn() const
{
    return m_view ? m_view->cursorPosition().column() : 0;
}

bool KateEditor::editorFocus() const
{
    return m_focus;
}

QString KateEditor::frameworkVersion() const
{
    return QStringLiteral(KTEXTEDITOR_VERSION_STRING);
}

void KateEditor::setCursorPosition(int line, int column)
{
    if (m_view)
        m_view->setCursorPosition(KTextEditor::Cursor(line, column));
}

void KateEditor::focusEditor()
{
    activateEditor();
}

// ------------------------------------------------------------ the keyboard

void KateEditor::activateEditor()
{
    if (!m_view)
        return;
    m_wantsInput = true;
    KateHost::instance()->activateView(m_view);
    if (!hasActiveFocus() && !m_activating) {
        m_activating = true;
        forceActiveFocus(Qt::MouseFocusReason);
        m_activating = false;
    }
    QT_WARNING_PUSH
    QT_WARNING_DISABLE_DEPRECATED
    if (QApplication::activeWindow() != m_container)
        QApplication::setActiveWindow(m_container);
    QT_WARNING_POP
    if (QWidget *proxy = m_view->focusProxy())
        proxy->setFocus(Qt::MouseFocusReason);
    else
        m_view->setFocus(Qt::MouseFocusReason);
    if (m_internal && !m_internal->hasFocus())
        ensureEditFocus();
}

void KateEditor::ensureEditFocus()
{
    // Kate enables its editing actions when its internal widget gets focus;
    // tell it, even when Qt doesn't consider the view's window active
    if (!m_internal)
        return;
    QFocusEvent in(QEvent::FocusIn, Qt::OtherFocusReason);
    QCoreApplication::sendEvent(m_internal, &in);
}

bool KateEditor::dispatchShortcut(QWidget *target, QKeyEvent *event)
{
    if (!m_view || event->key() == Qt::Key_unknown)
        return false;
    const auto mods = event->modifiers() & ~(Qt::KeypadModifier | Qt::GroupSwitchModifier);
    const QKeySequence seq(QKeyCombination(mods, Qt::Key(event->key())));
    const QList<QAction *> candidates = allActions();
    for (int pass = 0; pass < 2; ++pass) {
        for (QAction *a : candidates) {
            if (!a->shortcuts().contains(seq))
                continue;
            if (!a->isEnabled()) {
                if (pass == 0)
                    continue;   // first look for an enabled one
                ensureEditFocus();
                if (!a->isEnabled())
                    continue;
            }
            // some features (completion) also want the view's window active
            QT_WARNING_PUSH
            QT_WARNING_DISABLE_DEPRECATED
            if (QApplication::activeWindow() != m_container)
                QApplication::setActiveWindow(m_container);
            QT_WARNING_POP
            // ...and the widget the key was for focused (not, say, a search
            // field that had focus before)
            if (target && QApplication::focusWidget() != target)
                target->setFocus(Qt::OtherFocusReason);
            m_wantsInput = true;
            KateHost::instance()->activateView(m_view);
            a->trigger();
            return true;
        }
    }
    return false;
}

void KateEditor::deactivateEditor()
{
    m_wantsInput = false;
    QT_WARNING_PUSH
    QT_WARNING_DISABLE_DEPRECATED
    if (m_container && QApplication::activeWindow() == m_container)
        QApplication::setActiveWindow(nullptr);
    QT_WARNING_POP
}

void KateEditor::inputMethodEvent(QInputMethodEvent *event)
{
    if (m_internal) {
        QCoreApplication::sendEvent(m_internal, event);
        return;
    }
    NativeWidgetItem::inputMethodEvent(event);
}

QVariant KateEditor::inputMethodQuery(Qt::InputMethodQuery query) const
{
    // (positions are relative to the editor widget, which covers the item)
    if (m_internal)
        return m_internal->inputMethodQuery(query);
    return NativeWidgetItem::inputMethodQuery(query);
}

void KateEditor::keyPressEvent(QKeyEvent *event)
{
    if (m_internal) {
        if (m_shortcutFired) {   // Qt already ran Kate's action for this key
            m_shortcutFired = false;
            event->accept();
            return;
        }
        activateEditor();
        // Kate's shortcut keys: trigger the action once here (re-sending the
        // key would let Qt's shortcut map fire it a second time)
        if (dispatchShortcut(m_internal, event)) {
            event->accept();
            return;
        }
        std::unique_ptr<QEvent> copy(event->clone());
        QCoreApplication::sendEvent(m_internal, copy.get());
        event->setAccepted(copy->isAccepted());
        // Escape nobody wanted: Kate's plugins close their popups / tool views
        if (!copy->isAccepted() && event->key() == Qt::Key_Escape) {
            QKeyEvent esc(QEvent::ShortcutOverride, Qt::Key_Escape, Qt::NoModifier);
            Q_EMIT KateHost::instance()->mainWindow()->unhandledShortcutOverride(&esc);
        }
        return;
    }
    NativeWidgetItem::keyPressEvent(event);
}

void KateEditor::keyReleaseEvent(QKeyEvent *event)
{
    if (m_internal) {
        std::unique_ptr<QEvent> copy(event->clone());
        QCoreApplication::sendEvent(m_internal, copy.get());
        event->setAccepted(copy->isAccepted());
        return;
    }
    NativeWidgetItem::keyReleaseEvent(event);
}

void KateEditor::itemChange(ItemChange change, const ItemChangeData &value)
{
    if (change == ItemActiveFocusHasChanged && !m_activating) {
        // QML focus moved here (Tab, a popup closed) or away (a field was focused)
        if (value.boolValue)
            activateEditor();
        else
            deactivateEditor();
    }
    NativeWidgetItem::itemChange(change, value);
}

// ------------------------------------------------------------- the actions

bool KateEditor::triggerAction(const QString &name)
{
    const auto actions = allActions();
    for (QAction *a : actions) {
        if (a->objectName() == name && a->isEnabled()) {
            KateHost::instance()->activateView(m_view);
            a->trigger();
            return true;
        }
    }
    return false;
}

QStringList KateEditor::actionNames() const
{
    QStringList out;
    const auto actions = allActions();
    for (QAction *a : actions) {
        if (!a->objectName().isEmpty() && !out.contains(a->objectName()))
            out.append(a->objectName());
    }
    return out;
}

QPointF KateEditor::positionBelow(int line, int column) const
{
    if (!m_view)
        return {};
    const QPoint top = m_view->cursorToCoordinate(KTextEditor::Cursor(line, column));
    if (top.x() < 0 || top.y() < 0)
        return {};
    const QFont font = m_view->configValue(QStringLiteral("font")).value<QFont>();
    return QPointF(top.x(), top.y() + QFontMetrics(font).height() + 2);
}

void KateEditor::undo()
{
    triggerAction(QStringLiteral("edit_undo"));
}

void KateEditor::redo()
{
    triggerAction(QStringLiteral("edit_redo"));
}

QList<QAction *> KateEditor::allActions() const
{
    QList<QAction *> out;
    if (m_internal)
        out += m_internal->actions();
    if (m_view) {
        out += m_view->actions();
        out += m_view->findChildren<QAction *>();
        out += m_view->actionCollection()->actions();
        // the plugins' (LSP client: F2 rename, Alt+Return code actions…)
        out += KateHost::instance()->pluginActions();
    }
    return out;
}

void KateEditor::applyActionRules()
{
    // go to definition from Kate's action (menu, shortcut): tell Kreator too
    m_watchedDefinition.removeAll(nullptr);
    for (QAction *a : KateHost::instance()->pluginActions()) {
        if (a->objectName() == QLatin1String("lspclient_find_definition") && !m_watchedDefinition.contains(a)) {
            m_watchedDefinition.append(a);
            connect(a, &QAction::triggered, this, [this] {
                if (m_view && KateHost::instance()->activeView() == m_view) {
                    const auto c = m_view->cursorPosition();
                    Q_EMIT definitionRequested(c.line(), c.column());
                }
            });
        }
    }
    QList<QKeySequence> released;
    for (const QString &k : std::as_const(m_released))
        released.append(QKeySequence::fromString(k, QKeySequence::PortableText));
    const auto actions = allActions();
    for (QAction *a : actions) {
        if (m_disabled.contains(a->objectName())) {
            a->setShortcuts({});
            a->setEnabled(false);
            a->setVisible(false);
            continue;
        }
        auto shortcuts = a->shortcuts();
        const auto before = shortcuts.size();
        shortcuts.removeIf([&](const QKeySequence &s) {
            return released.contains(s);
        });
        if (shortcuts.size() != before)
            a->setShortcuts(shortcuts);
    }
}

QStringList KateEditor::releasedShortcuts() const
{
    return m_released;
}

void KateEditor::setReleasedShortcuts(const QStringList &keys)
{
    if (keys == m_released)
        return;
    m_released = keys;
    applyActionRules();
    Q_EMIT releasedShortcutsChanged();
}

QStringList KateEditor::disabledActions() const
{
    return m_disabled;
}

void KateEditor::setDisabledActions(const QStringList &names)
{
    if (names == m_disabled)
        return;
    m_disabled = names;
    applyActionRules();
    Q_EMIT disabledActionsChanged();
}

// --------------------------------------------------------- language server

QStringList KateEditor::languageServer() const
{
    return m_languageServer;
}

void KateEditor::setLanguageServer(const QStringList &command)
{
    if (command == m_languageServer)
        return;
    m_languageServer = command;
    updateLanguage();
}

QString KateEditor::projectRoot() const
{
    return m_projectRoot;
}

void KateEditor::setProjectRoot(const QString &root)
{
    if (root == m_projectRoot)
        return;
    m_projectRoot = root;
    updateLanguage();
}

bool KateEditor::languageFeatures() const
{
    return KateHost::instance()->languagePluginLoaded();
}

QString KateEditor::languageProblem() const
{
    return m_languageProblem;
}

void KateEditor::updateLanguage()
{
    KateHost *host = KateHost::instance();
    host->setProject(m_projectRoot, m_languageServer);
    if (!m_languageServer.isEmpty() && !host->languagePluginLoaded()) {
        QString why;
        if (!host->loadLanguagePlugin(&why))
            m_languageProblem = why;
        else
            m_languageProblem.clear();
        applyActionRules();
    }
    Q_EMIT languageChanged();
}

// ---------------------------------------------------------------- settings

void KateEditor::configureEditor()
{
    // like Kate's settings dialog: the editor's pages, then the LSP client's
    auto *editor = KTextEditor::Editor::instance();
    KPageDialog dialog;
    dialog.setWindowTitle(i18nc("@title:window", "Configure Editor"));
    dialog.setFaceType(KPageDialog::List);
    dialog.setStandardButtons(QDialogButtonBox::Ok | QDialogButtonBox::Apply | QDialogButtonBox::Cancel);
    QList<KTextEditor::ConfigPage *> pages;
    for (int i = 0; i < editor->configPages(); ++i) {
        if (auto *p = editor->configPage(i, &dialog))
            pages.append(p);
    }
    pages += KateHost::instance()->pluginConfigPages(&dialog);
    QPushButton *apply = dialog.button(QDialogButtonBox::Apply);
    apply->setEnabled(false);
    for (auto *p : std::as_const(pages)) {
        KPageWidgetItem *item = dialog.addPage(p, p->name());
        item->setHeader(p->fullName());
        item->setIcon(p->icon());
        connect(p, &KTextEditor::ConfigPage::changed, apply, [apply] {
            apply->setEnabled(true);
        });
    }
    const auto applyAll = [&pages, apply] {
        for (auto *p : std::as_const(pages))
            p->apply();
        apply->setEnabled(false);
    };
    connect(apply, &QPushButton::clicked, &dialog, applyAll);
    // over Kreator's window
    dialog.winId();
    if (QWindow *h = dialog.windowHandle(); h && quickWindow())
        h->setTransientParent(quickWindow());
    if (dialog.exec() == QDialog::Accepted)
        applyAll();
    applyActionRules();   // the dialog may have changed shortcuts
}
