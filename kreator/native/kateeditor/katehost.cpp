#include "katehost.h"

#include "nativeitem.h"
#include "sharedsettings.h"

#include <KTextEditor/Application>
#include <KTextEditor/ConfigPage>
#include <KTextEditor/Cursor>
#include <KTextEditor/Document>
#include <KTextEditor/Editor>
#include <KTextEditor/MainWindow>
#include <KTextEditor/View>

#include <KActionCollection>
#include <KPluginFactory>
#include <KPluginMetaData>
#include <KXMLGUIBuilder>
#include <KXMLGUIClient>
#include <KXMLGUIFactory>

#include <QAction>
#include <QApplication>
#include <QDir>
#include <QFileInfo>
#include <QMainWindow>
#include <QMenu>
#include <QTimer>
#include <QTabWidget>
#include <QVBoxLayout>

// ------------------------------------------------------------ project info

static QString findRoot(const QString &file)
{
    // like Kreator: a folder with .qmlls.ini, else the git root
    QDir dir = QFileInfo(file).absoluteDir();
    QString git;
    while (true) {
        if (dir.exists(QStringLiteral(".qmlls.ini")))
            return dir.absolutePath();
        if (git.isEmpty() && dir.exists(QStringLiteral(".git")))
            git = dir.absolutePath();
        if (!dir.cdUp())
            break;
    }
    return git;
}

QString KreatorProjectInfo::projectBaseDir() const
{
    return m_root;
}

QObjectList KreatorProjectInfo::projects() const
{
    return m_project ? QObjectList{m_project} : QObjectList{};
}

void KreatorProjectInfo::set(const QString &root, const QStringList &qmlls)
{
    if (root == m_root && qmlls == m_qmlls)
        return;
    if (m_project && root != m_root) {
        Q_EMIT projectRemoved(m_project);
        m_project->deleteLater();
        m_project = nullptr;
    }
    m_qmlls = qmlls;
    if (root != m_root && !root.isEmpty()) {
        m_project = new QObject(this);
        m_project->setProperty("name", QFileInfo(root).fileName());
        m_project->setProperty("baseDir", root);
        m_root = root;
        Q_EMIT projectAdded(m_project);
    }
    m_root = root;
    Q_EMIT changed();
}

QString KreatorProjectInfo::projectBaseDirForDocument(KTextEditor::Document *document)
{
    if (!document || !document->url().isLocalFile())
        return {};
    const QString file = document->url().toLocalFile();
    if (!m_root.isEmpty() && file.startsWith(m_root + QLatin1Char('/')))
        return m_root;
    return findRoot(file);
}

QVariantMap KreatorProjectInfo::projectMapForDocument(KTextEditor::Document *)
{
    // Kreator's qmlls: the bridge to the qmlls Kreator runs (Kate's default
    // is a qmlls of its own, called "qmlls", which isn't on every PATH)
    if (m_qmlls.isEmpty())
        return {};
    QVariantMap qml{{QStringLiteral("command"), m_qmlls}};
    QVariantMap servers{{QStringLiteral("qml"), qml}};
    QVariantMap lsp{{QStringLiteral("servers"), servers}};
    return {{QStringLiteral("lspclient"), lsp}};
}

// ------------------------------------------------------------------ relays
// KTextEditor::Application and ::MainWindow call these by name

class KateAppRelay : public QObject
{
    Q_OBJECT
public:
    explicit KateAppRelay(KateHost *host)
        : QObject(host)
        , m_host(host)
    {
    }

public Q_SLOTS:
    bool quit()
    {
        return false;
    }
    QList<KTextEditor::MainWindow *> mainWindows()
    {
        return {m_host->mainWindow()};
    }
    KTextEditor::MainWindow *activeMainWindow()
    {
        return m_host->mainWindow();
    }
    QList<KTextEditor::Document *> documents()
    {
        // (the shown one: the other tabs' documents are Kreator's to change,
        // see KateHost::findUrl)
        if (KTextEditor::View *v = m_host->activeView())
            return {v->document()};
        return {};
    }
    KTextEditor::Document *findUrl(const QUrl &url)
    {
        return m_host->findUrl(url);
    }
    KTextEditor::Document *openUrl(const QUrl &url, const QString &encoding = QString())
    {
        Q_UNUSED(encoding)
        KTextEditor::View *v = m_host->openUrl(url);
        return v ? v->document() : nullptr;
    }
    bool closeDocument(KTextEditor::Document *)
    {
        return false;   // Kreator's documents are closed by Kreator
    }
    bool closeDocuments(const QList<KTextEditor::Document *> &)
    {
        return false;
    }
    KTextEditor::Plugin *plugin(const QString &name)
    {
        return m_host->plugin(name);
    }

private:
    KateHost *m_host;
};

class KateWindowRelay : public QObject
{
    Q_OBJECT
public:
    KateWindowRelay(KateHost *host, QMainWindow *window)
        : QObject(host)
        , m_host(host)
        , m_window(window)
    {
    }

public Q_SLOTS:
    QWidget *window()
    {
        // The editor: KTextEditor puts the completion popup into this widget
        // (a hidden one would hide it), and the plugins parent their dialogs
        // to it (they get Kreator's window as transient parent when shown,
        // see NativeWidgetItem). Before there is a view: none, so a new view
        // keeps its completion popup to itself.
        return m_host->activeView();
    }
    KXMLGUIFactory *guiFactory()
    {
        return m_host->factory();
    }
    QList<KTextEditor::View *> views()
    {
        return m_host->views();
    }
    KTextEditor::View *activeView()
    {
        return m_host->activeView();
    }
    KTextEditor::View *activateView(KTextEditor::Document *document)
    {
        m_host->activateDocument(document);
        const auto views = m_host->views();
        for (auto *v : views) {
            if (v->document() == document) {
                m_host->activateView(v);
                return v;
            }
        }
        return m_host->activeView();
    }
    KTextEditor::View *openUrl(const QUrl &url, const QString &encoding = QString())
    {
        Q_UNUSED(encoding)
        return m_host->openUrl(url);
    }
    bool closeView(KTextEditor::View *)
    {
        return false;
    }
    void splitView(Qt::Orientation)
    {
    }
    bool closeSplitView(KTextEditor::View *)
    {
        return false;
    }
    bool viewsInSameSplitView(KTextEditor::View *, KTextEditor::View *)
    {
        return false;
    }
    // no view bars of the main window: the views keep their own (search…)
    QWidget *createViewBar(KTextEditor::View *)
    {
        return nullptr;
    }
    void deleteViewBar(KTextEditor::View *)
    {
    }
    void addWidgetToViewBar(KTextEditor::View *, QWidget *)
    {
    }
    void showViewBar(KTextEditor::View *)
    {
    }
    void hideViewBar(KTextEditor::View *)
    {
    }
    void insertWidgetInStatusbar(QWidget *w)
    {
        if (w) {
            w->hide();
            w->setParent(m_window);
        }
    }
    QWidget *createToolView(KTextEditor::Plugin *plugin,
                            const QString &identifier,
                            KTextEditor::MainWindow::ToolViewPosition pos,
                            const QIcon &icon,
                            const QString &text)
    {
        Q_UNUSED(pos)
        return m_host->createToolView(plugin, identifier, icon, text);
    }
    QWidget *toolviewForName(const QString &identifier)
    {
        return m_host->toolViewForName(identifier);
    }
    QWidget *activeViewToolView(int)
    {
        return nullptr;
    }
    bool moveToolView(QWidget *, KTextEditor::MainWindow::ToolViewPosition)
    {
        return false;
    }
    bool showToolView(QWidget *widget)
    {
        return m_host->showToolView(widget);
    }
    bool hideToolView(QWidget *widget)
    {
        return m_host->hideToolView(widget);
    }
    bool showPluginConfigPage(KTextEditor::Plugin *, int)
    {
        return false;
    }
    QObject *pluginView(const QString &name)
    {
        return m_host->pluginView(name);
    }
    bool addWidget(QWidget *)
    {
        return false;
    }
    QWidgetList widgets() const
    {
        return {};
    }
    bool removeWidget(QWidget *)
    {
        return false;
    }
    QWidget *activeWidget()
    {
        return m_host->activeView();
    }
    void activateWidget(QWidget *)
    {
    }
    bool showMessage(const QVariantMap &map)
    {
        return m_host->showMessage(map);
    }
    void addPositionToHistory(const QUrl &, KTextEditor::Cursor)
    {
    }

private:
    KateHost *m_host;
    QMainWindow *m_window;
};

// -------------------------------------------------------------------- host

KateHost *KateHost::instance()
{
    static QPointer<KateHost> host;
    if (!host)
        host = new KateHost(qApp);
    return host;
}

KateHost::KateHost(QObject *parent)
    : QObject(parent)
{
    // the settings must be in place before the editor reads them
    SharedSettings::importFromKate(SharedSettings::editorGroups());
    auto *editor = KTextEditor::Editor::instance();
    // changes made in Kreator (Kate's settings dialog) go back to Kate
    connect(editor, &KTextEditor::Editor::configChanged, this, [] {
        SharedSettings::exportToKate(SharedSettings::editorGroups());
    });

    m_guiWindow = new QMainWindow;
    m_guiWindow->setObjectName(QStringLiteral("KreatorKateGui"));
    m_guiWindow->setAttribute(Qt::WA_QuitOnClose, false);
    NativeWidgetItem::registerKateWidget(m_guiWindow);
    m_factory = new KXMLGUIFactory(new KXMLGUIBuilder(m_guiWindow), this);

    m_toolArea = new QTabWidget;
    m_toolArea->setObjectName(QStringLiteral("KreatorKateToolArea"));
    m_toolArea->setDocumentMode(true);
    NativeWidgetItem::registerKateWidget(m_toolArea);

    m_appRelay = new KateAppRelay(this);
    m_windowRelay = new KateWindowRelay(this, m_guiWindow);
    m_application = new KTextEditor::Application(m_appRelay);
    m_mainWindow = new KTextEditor::MainWindow(m_windowRelay);
    editor->setApplication(m_application);

    m_project = new KreatorProjectInfo(this);

    connect(qApp, &QCoreApplication::aboutToQuit, this, [this] {
        m_toolArea->hide();
    });
}

void KateHost::addView(KTextEditor::View *view)
{
    if (!view || m_views.contains(view))
        return;
    m_views.append(view);
    Q_EMIT m_mainWindow->viewCreated(view);
    if (!m_active)
        activateView(view);
}

void KateHost::removeView(KTextEditor::View *view)
{
    m_views.removeAll(view);
    m_views.removeAll(nullptr);
    if (m_guiClient == view) {
        m_factory->removeClient(view);
        m_guiClient = nullptr;
    }
    if (m_active == view) {
        m_active = nullptr;
        if (!m_views.isEmpty())
            activateView(m_views.last());
        else
            Q_EMIT m_mainWindow->viewChanged(nullptr);
    }
}

void KateHost::activateView(KTextEditor::View *view)
{
    if (view == m_active)
        return;
    m_active = view;
    setGuiClient(view);
    Q_EMIT m_mainWindow->viewChanged(view);
}

void KateHost::setGuiClient(KTextEditor::View *view)
{
    // the active view's actions and menus (its context menu, merged with the
    // plugins' entries, comes from the factory)
    if (view == m_guiClient)
        return;
    if (m_guiClient)
        m_factory->removeClient(m_guiClient);
    m_guiClient = view;
    if (view)
        m_factory->addClient(view);
    Q_EMIT actionsChanged();
}

KTextEditor::View *KateHost::activeView() const
{
    return m_active;
}

QList<KTextEditor::View *> KateHost::views() const
{
    QList<KTextEditor::View *> out;
    for (const auto &v : m_views) {
        if (v)
            out.append(v);
    }
    return out;
}

void KateHost::setProject(const QString &root, const QStringList &qmlls)
{
    m_project->set(root, qmlls);
}

bool KateHost::loadLanguagePlugin(QString *error)
{
    if (m_lsp)
        return true;
    const KPluginMetaData md = KPluginMetaData::findPluginById(QStringLiteral("kf6/ktexteditor"), QStringLiteral("lspclientplugin"));
    if (!md.isValid()) {
        if (error)
            *error = QStringLiteral("Kate's LSP client plugin is not installed (it comes with Kate)");
        return false;
    }
    // Kate's LSP settings and settings.json
    SharedSettings::importFromKate({QStringLiteral("lspclient")});
    SharedSettings::shareLanguageServerSettings();
    SharedSettings::allowServerCommand(m_project->serverCommand());
    const auto result = KPluginFactory::instantiatePlugin<KTextEditor::Plugin>(md, this, {md.pluginId()});
    if (!result) {
        if (error)
            *error = QStringLiteral("Kate's LSP client plugin could not be loaded: %1").arg(result.errorText);
        return false;
    }
    m_lsp = result.plugin;
    Q_EMIT m_application->pluginCreated(md.pluginId(), m_lsp);
    // changes in its settings go back to Kate
    if (m_lsp->metaObject()->indexOfSignal("update()") >= 0)
        connect(m_lsp, SIGNAL(update()), this, SLOT(sharePluginSettings()));
    m_lspView = m_lsp->createView(m_mainWindow);
    Q_EMIT m_mainWindow->pluginViewCreated(md.pluginId(), m_lspView);
    // the views that already exist
    const auto views = this->views();
    for (auto *v : views)
        Q_EMIT m_mainWindow->viewCreated(v);
    if (m_active)
        Q_EMIT m_mainWindow->viewChanged(m_active);
    Q_EMIT actionsChanged();
    return true;
}

void KateHost::sharePluginSettings()
{
    SharedSettings::exportToKate({QStringLiteral("lspclient")});
}

QList<QAction *> KateHost::pluginActions() const
{
    QList<QAction *> out;
    const auto clients = m_factory->clients();
    for (KXMLGUIClient *c : clients) {
        if (c == m_guiClient.data() || !c->actionCollection())
            continue;
        out += c->actionCollection()->actions();
    }
    return out;
}

QList<KTextEditor::ConfigPage *> KateHost::pluginConfigPages(QWidget *parent) const
{
    QList<KTextEditor::ConfigPage *> out;
    if (m_lsp) {
        for (int i = 0; i < m_lsp->configPages(); ++i) {
            if (auto *p = m_lsp->configPage(i, parent))
                out.append(p);
        }
    }
    return out;
}

KTextEditor::Document *KateHost::findUrl(const QUrl &url) const
{
    // Only the shown document counts as open: a file of another tab is opened
    // as a side document (see Side), so that Kreator shows it (go to
    // definition) or applies the change to its document (rename)
    if (m_active && m_active->document()->url() == url)
        return m_active->document();
    return nullptr;
}

KTextEditor::View *KateHost::openUrl(const QUrl &url)
{
    if (!url.isLocalFile())
        return nullptr;
    if (m_active && m_active->document()->url() == url)
        return m_active;
    if (auto it = m_side.constFind(url); it != m_side.constEnd())
        return it->view;
    // a side document (see Side), settled when the plugin is done
    Side side;
    side.doc = KTextEditor::Editor::instance()->createDocument(this);
    side.doc->setModifiedOnDiskWarning(false);
    if (!side.doc->openUrl(url)) {
        delete side.doc;
        return nullptr;
    }
    side.basis = side.doc->text();
    side.view = side.doc->createView(m_guiWindow, m_mainWindow);
    side.view->hide();
    m_side.insert(url, side);
    QTimer::singleShot(0, this, &KateHost::settleSideDocuments);
    return side.view;
}

bool KateHost::activateDocument(KTextEditor::Document *document)
{
    // a plugin brings a side document forward: show that file
    for (auto it = m_side.begin(); it != m_side.end(); ++it) {
        if (it->doc == document) {
            settleSideDocuments();
            return true;
        }
    }
    return false;
}

void KateHost::settleSideDocuments()
{
    const auto sides = m_side;
    m_side.clear();
    for (auto it = sides.begin(); it != sides.end(); ++it) {
        const Side &side = it.value();
        const QString path = it.key().toLocalFile();
        const QString text = side.doc->text();
        const KTextEditor::Cursor cursor = side.view->cursorPosition();
        if (text != side.basis) {
            // edited (rename, code action): Kreator applies it as an unsaved
            // change; a tab's document of the file (not shown) gets it too
            for (auto *v : views()) {
                if (v != m_active && v->document()->url() == it.key() && v->document()->text() == side.basis)
                    v->document()->setText(text);
            }
            Q_EMIT fileEdited(path, side.basis, text);
        } else if (sides.size() == 1) {
            // only looked at (go to definition): Kreator shows the file there
            Q_EMIT openRequested(path);
            if (m_active && m_active->document()->url() == it.key()) {
                m_active->setCursorPosition(cursor);
                Q_EMIT m_mainWindow->viewChanged(m_active);
            }
        }
        side.doc->setModified(false);
        side.doc->deleteLater();
    }
}

QWidget *KateHost::createToolView(KTextEditor::Plugin *, const QString &identifier, const QIcon &icon, const QString &text)
{
    if (QWidget *existing = m_toolViews.value(identifier))
        return existing;
    // like Kate's tool views: a container with a layout the plugin fills
    auto *container = new QWidget;
    container->setObjectName(identifier);
    auto *layout = new QVBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    m_toolArea->addTab(container, icon, text);
    m_toolViews.insert(identifier, container);
    connect(container, &QObject::destroyed, this, [this, identifier] {
        m_toolViews.remove(identifier);
        Q_EMIT toolViewsChanged();
    });
    Q_EMIT toolViewsChanged();
    return container;
}

static QWidget *toolViewOf(const QHash<QString, QPointer<QWidget>> &views, QWidget *w)
{
    for (QWidget *p = w; p; p = p->parentWidget()) {
        for (const auto &v : views) {
            if (v == p)
                return p;
        }
    }
    return nullptr;
}

bool KateHost::showToolView(QWidget *widget)
{
    QWidget *tv = toolViewOf(m_toolViews, widget);
    if (!tv)
        return false;
    m_toolArea->setCurrentWidget(tv);
    Q_EMIT toolAreaRequested(true);
    return true;
}

bool KateHost::hideToolView(QWidget *widget)
{
    QWidget *tv = toolViewOf(m_toolViews, widget);
    if (!tv)
        return false;
    if (m_toolArea->currentWidget() == tv)
        Q_EMIT toolAreaRequested(false);
    return true;
}

QWidget *KateHost::toolViewForName(const QString &identifier) const
{
    return m_toolViews.value(identifier);
}

QObject *KateHost::pluginView(const QString &name) const
{
    if (name == QLatin1String("kateprojectplugin"))
        return m_project;
    if (m_lsp && name == QLatin1String("lspclientplugin"))
        return m_lspView;
    return nullptr;
}

KTextEditor::Plugin *KateHost::plugin(const QString &name) const
{
    if (name == QLatin1String("kateprojectplugin"))
        return m_project;
    if (name == QLatin1String("lspclientplugin"))
        return m_lsp;
    return nullptr;
}

bool KateHost::showMessage(const QVariantMap &message)
{
    const QString text = message.value(QStringLiteral("text")).toString();
    const QString type = message.value(QStringLiteral("type")).toString();
    if (!text.isEmpty())
        Q_EMIT this->message(text, type);
    return true;
}

#include "katehost.moc"
