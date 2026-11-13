// Kate's editor (KTextEditor) as a QML item.
//
// The editor's view is a QWidget shown over the item (see NativeWidgetItem).
// It is registered with KateHost, which provides what Kate's main window
// would: with it, Kate's LSP client plugin works in the view (completion,
// diagnostics, hover, go to definition, rename…).

#pragma once

#include "nativeitem.h"

#include <QHash>
#include <QList>
#include <QPointer>
#include <QStringList>

class QKeyEvent;
class QStackedLayout;
class QInputMethodEvent;
class QAction;

namespace KTextEditor {
class Document;
class View;
}

class KateEditor : public NativeWidgetItem
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QString text READ text WRITE setText NOTIFY textChanged)
    Q_PROPERTY(QString mode READ mode WRITE setMode NOTIFY modeChanged)
    // the file shown (the document gets its URL, for the language server; the
    // text is still Kreator's, which can differ from the file's)
    Q_PROPERTY(QString fileName READ fileName WRITE setFileName NOTIFY fileNameChanged)
    // which of Kreator's documents is shown. Each has a Kate document (and
    // view) of its own, kept while it is open (see openKeys), like Kate's tabs:
    // switching back keeps its highlighting, cursor, scroll position and undo
    Q_PROPERTY(QString documentKey READ documentKey WRITE setDocumentKey NOTIFY documentKeyChanged)
    // Kreator's open documents: the Kate documents of others are dropped
    Q_PROPERTY(QStringList openKeys READ openKeys WRITE setOpenKeys NOTIFY openKeysChanged)
    // the shown document was shown here before (its view kept its place)
    Q_PROPERTY(bool documentReused READ documentReused NOTIFY documentKeyChanged)
    Q_PROPERTY(int cursorLine READ cursorLine NOTIFY cursorPositionChanged)
    Q_PROPERTY(int cursorColumn READ cursorColumn NOTIFY cursorPositionChanged)
    Q_PROPERTY(bool editorFocus READ editorFocus NOTIFY editorFocusChanged)
    Q_PROPERTY(QString frameworkVersion READ frameworkVersion CONSTANT)
    // keys the host application owns: Kate's actions lose them (e.g. Ctrl+S)
    Q_PROPERTY(QStringList releasedShortcuts READ releasedShortcuts WRITE setReleasedShortcuts NOTIFY releasedShortcutsChanged)
    // Kate actions that must not run embedded (e.g. file_save: the host saves)
    Q_PROPERTY(QStringList disabledActions READ disabledActions WRITE setDisabledActions NOTIFY disabledActionsChanged)
    // Kate's LSP client: the language server command for QML (empty: off), and
    // the project folder (the server's root)
    Q_PROPERTY(QStringList languageServer READ languageServer WRITE setLanguageServer NOTIFY languageChanged)
    Q_PROPERTY(QString projectRoot READ projectRoot WRITE setProjectRoot NOTIFY languageChanged)
    Q_PROPERTY(bool languageFeatures READ languageFeatures NOTIFY languageChanged)
    Q_PROPERTY(QString languageProblem READ languageProblem NOTIFY languageChanged)

public:
    explicit KateEditor(QQuickItem *parent = nullptr);
    ~KateEditor() override;

    QString text() const;
    void setText(const QString &text);
    QString mode() const;
    void setMode(const QString &mode);
    QString fileName() const;
    void setFileName(const QString &name);
    QString documentKey() const;
    void setDocumentKey(const QString &key);
    QStringList openKeys() const;
    void setOpenKeys(const QStringList &keys);
    bool documentReused() const;
    int cursorLine() const;
    int cursorColumn() const;
    bool editorFocus() const;
    QString frameworkVersion() const;
    QStringList releasedShortcuts() const;
    void setReleasedShortcuts(const QStringList &keys);
    QStringList disabledActions() const;
    void setDisabledActions(const QStringList &names);
    QStringList languageServer() const;
    void setLanguageServer(const QStringList &command);
    QString projectRoot() const;
    void setProjectRoot(const QString &root);
    bool languageFeatures() const;
    QString languageProblem() const;

    // 0-based, like Kreator's LSP positions
    Q_INVOKABLE void setCursorPosition(int line, int column);
    Q_INVOKABLE void focusEditor();
    // Kate's settings dialog: the editor's pages and the LSP client's (the
    // settings are shared with Kate)
    Q_INVOKABLE void configureEditor();
    // undo/redo of the editor's own history
    Q_INVOKABLE void undo();
    Q_INVOKABLE void redo();
    // run one of Kate's actions by name (e.g. "lspclient_find_references");
    // false if there is no such (enabled) action
    Q_INVOKABLE bool triggerAction(const QString &name);
    // names of the actions with these words in their text (for tests / menus)
    Q_INVOKABLE QStringList actionNames() const;
    // where a text position is drawn, in item coordinates: the bottom left of
    // the line (to place a popup under it)
    Q_INVOKABLE QPointF positionBelow(int line, int column) const;

Q_SIGNALS:
    void textChanged();
    // changed by typing / editing in the editor (not by setText)
    void textEdited();
    void modeChanged();
    void fileNameChanged();
    void documentKeyChanged();
    void openKeysChanged();
    void cursorPositionChanged();
    void editorFocusChanged();
    void releasedShortcutsChanged();
    void disabledActionsChanged();
    void languageChanged();
    // Kate (go to definition…) wants this file shown; Kreator opens it, right
    // away, and shows it in this editor
    void openFileRequested(const QString &path);
    // Kate (rename, code action) changed a file that isn't shown: apply it to
    // that file in Kreator (as an unsaved change); basis is the text the
    // change was made to
    void fileEditRequested(const QString &path, const QString &basis, const QString &text);
    // go to definition was asked for this position (Ctrl+click, or Kate's
    // action): Kreator can describe a C++ type, which has no file to open
    void definitionRequested(int line, int column);
    // a message from Kate's plugins (type: Error, Warning, Info, Log)
    void message(const QString &text, const QString &type);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void itemChange(ItemChange change, const ItemChangeData &value) override;
    // keys that reach Kreator's window while the editor has (QML) focus
    void keyPressEvent(QKeyEvent *event) override;
    void keyReleaseEvent(QKeyEvent *event) override;
    void inputMethodEvent(QInputMethodEvent *event) override;
    QVariant inputMethodQuery(Qt::InputMethodQuery query) const override;

private:
    void bindUrl();
    void clearUndo();
    void updateLanguage();

    // a Kreator document's Kate document and view
    struct Entry {
        KTextEditor::Document *doc = nullptr;
        QPointer<KTextEditor::View> view;
        QWidget *internal = nullptr;
        QString mode;
        bool fresh = true;   // no text from Kreator yet (its undo starts after it)
    };
    Entry createEntry();
    void showEntry(const Entry &entry);
    void dropEntry(Entry &entry);
    QHash<QString, Entry> m_entries;
    QWidget *m_container = nullptr;     // the native widget shown (holds the views)
    QStackedLayout *m_stack = nullptr;
    QList<QPointer<KTextEditor::View>> m_watchedViews;   // views the key rules were applied to
    QStringList m_openKeys;
    bool m_reused = false;

    KTextEditor::Document *m_doc = nullptr;
    QPointer<KTextEditor::View> m_view;
    QString m_fileName;
    QString m_mode;
    QString m_documentKey;
    bool m_freshDocument = false;
    bool m_settingText = false;
    bool m_focus = false;
    QStringList m_languageServer;
    QString m_projectRoot;
    QString m_languageProblem;
    // keyboard input for the editor: Qt widgets only enable Kate's editing
    // actions (arrows, delete…) in the active window, which an embedded
    // view never becomes by itself on Wayland
    void activateEditor();
    void deactivateEditor();
    bool m_wantsInput = false;
    bool m_activating = false;
    // Qt's shortcut map already fired one of Kate's actions for the key now
    // being delivered (Qt Quick tries shortcuts before the key press)
    bool m_shortcutFired = false;
    // deliver Kate's shortcut keys (arrows, Backspace, Ctrl+F…) to its actions
    // ourselves: Qt only fires them in the active window
    bool dispatchShortcut(QWidget *target, QKeyEvent *event);
    void ensureEditFocus();
    QWidget *m_internal = nullptr;   // KateViewInternal, where the editing actions live
    QStringList m_released;
    QStringList m_disabled;
    void applyActionRules();
    QList<QAction *> allActions() const;
    bool isKateAction(QAction *a) const;
    QList<QPointer<QAction>> m_watchedDefinition;
};
