// What Kate provides to its plugins, provided by Kreator instead: an
// application and a main window (KTextEditor::Application / MainWindow), with
// an XMLGUI factory for the plugins' actions and menus, tool views, and the
// project information Kate's project plugin would give. With it, Kreator
// loads Kate's LSP client plugin (installed with Kate), so completion,
// diagnostics, hover, go to definition, rename… in the editor are Kate's, and
// get Kate's updates.
//
// One per process (KateHost::instance()); the editors register their views.

#pragma once

#include <KTextEditor/Plugin>

#include <QHash>
#include <QIcon>
#include <QList>
#include <QObject>
#include <QPointer>
#include <QStringList>
#include <QUrl>
#include <QVariantMap>

class QAction;
class QMainWindow;
class QTabWidget;
class KXMLGUIClient;
class KXMLGUIFactory;

namespace KTextEditor {
class Application;
class ConfigPage;
class Cursor;
class Document;
class MainWindow;
class View;
}

// What Kate's project plugin would say about a document: Kreator's project
// folder, and the language server to use (Kreator's qmlls).
class KreatorProjectInfo : public KTextEditor::Plugin
{
    Q_OBJECT
    Q_PROPERTY(QString projectBaseDir READ projectBaseDir NOTIFY changed)
    Q_PROPERTY(QObjectList projects READ projects NOTIFY changed)
public:
    using KTextEditor::Plugin::Plugin;
    QObject *createView(KTextEditor::MainWindow *) override
    {
        return nullptr;
    }
    QString projectBaseDir() const;
    QObjectList projects() const;
    QStringList serverCommand() const
    {
        return m_qmlls;
    }
    void set(const QString &root, const QStringList &qmlls);

public Q_SLOTS:
    QString projectBaseDirForDocument(KTextEditor::Document *document);
    QVariantMap projectMapForDocument(KTextEditor::Document *document);

Q_SIGNALS:
    void changed();
    // (the project plugin's signals, which the LSP client listens to)
    void projectAdded(QObject *project);
    void projectRemoved(QObject *project);

private:
    QString m_root;
    QStringList m_qmlls;
    QObject *m_project = nullptr;
};

class KateHost : public QObject
{
    Q_OBJECT
public:
    static KateHost *instance();

    KTextEditor::MainWindow *mainWindow() const
    {
        return m_mainWindow;
    }
    KXMLGUIFactory *factory() const
    {
        return m_factory;
    }
    QTabWidget *toolArea() const
    {
        return m_toolArea;
    }

    // the editors' views; the active one gets the plugins' attention
    void addView(KTextEditor::View *view);
    void removeView(KTextEditor::View *view);
    void activateView(KTextEditor::View *view);
    KTextEditor::View *activeView() const;
    QList<KTextEditor::View *> views() const;

    // Kate's LSP client (once per process); false + why if it can't be loaded
    bool loadLanguagePlugin(QString *error = nullptr);
    bool languagePluginLoaded() const
    {
        return m_lsp != nullptr;
    }
    // the plugins' actions (with their shortcuts), for the editor's key dispatch
    QList<QAction *> pluginActions() const;
    // config pages of the loaded plugins, for Kreator's "Configure Editor…"
    QList<KTextEditor::ConfigPage *> pluginConfigPages(QWidget *parent) const;

    void setProject(const QString &root, const QStringList &qmlls);

    // the main window / application interface (called through the relays)
    KTextEditor::View *openUrl(const QUrl &url);
    KTextEditor::Document *findUrl(const QUrl &url) const;
    QWidget *createToolView(KTextEditor::Plugin *plugin, const QString &identifier, const QIcon &icon, const QString &text);
    bool showToolView(QWidget *widget);
    bool hideToolView(QWidget *widget);
    QWidget *toolViewForName(const QString &identifier) const;
    QObject *pluginView(const QString &name) const;
    KTextEditor::Plugin *plugin(const QString &name) const;
    bool showMessage(const QVariantMap &message);

Q_SIGNALS:
    // a plugin wants this file shown (go to definition…); the active editor
    // handles it right away (KateEditor::openFileRequested)
    void openRequested(const QString &path);
    // a plugin changed a file that isn't shown (rename, code action): its
    // text before (from disk) and after, for Kreator to apply as an unsaved
    // change (KateEditor::fileEditRequested)
    void fileEdited(const QString &path, const QString &basis, const QString &text);
    // a message from a plugin for the user (type: Error, Warning, Info, Log)
    void message(const QString &text, const QString &type);
    // a plugin showed / hid one of its tool views
    void toolAreaRequested(bool show);
    void toolViewsChanged();
    // plugin actions were added (their shortcuts need the editor's key rules)
    void actionsChanged();

private Q_SLOTS:
    void sharePluginSettings();

private:
    // Files a plugin opens that aren't shown are loaded into side documents
    // first: a plugin either moves the cursor there (go to definition: then
    // Kreator shows the file) or edits it (rename: then Kreator applies the
    // edit). Decided once the plugin is done (next event loop turn).
    struct Side {
        KTextEditor::Document *doc = nullptr;
        KTextEditor::View *view = nullptr;
        QString basis;
    };
    QHash<QUrl, Side> m_side;
    void settleSideDocuments();
    bool activateDocument(KTextEditor::Document *document);
    friend class KateWindowRelay;

    explicit KateHost(QObject *parent = nullptr);
    void setGuiClient(KTextEditor::View *view);

    KTextEditor::Application *m_application = nullptr;
    KTextEditor::MainWindow *m_mainWindow = nullptr;
    QObject *m_appRelay = nullptr;
    QObject *m_windowRelay = nullptr;
    QMainWindow *m_guiWindow = nullptr;   // never shown: holds the XMLGUI containers
    KXMLGUIFactory *m_factory = nullptr;
    QTabWidget *m_toolArea = nullptr;
    QList<QPointer<KTextEditor::View>> m_views;
    QPointer<KTextEditor::View> m_active;
    QPointer<KTextEditor::View> m_guiClient;
    KreatorProjectInfo *m_project = nullptr;
    KTextEditor::Plugin *m_lsp = nullptr;
    QObject *m_lspView = nullptr;
    QHash<QString, QPointer<QWidget>> m_toolViews;
};
