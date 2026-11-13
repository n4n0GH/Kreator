#include "sharedsettings.h"

#include <KConfigGroup>
#include <KSharedConfig>

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSet>
#include <QStandardPaths>
#include <QVariant>

namespace
{
struct Override {
    const char *group;
    const char *key;
    const char *value;
};

// Kreator's own values, never taken from or given to Kate
const Override s_overrides[] = {
    {"KTextEditor Document", "Swap File Mode", "0"},
    {"KTextEditor Document", "Auto Save", "false"},
    {"KTextEditor Document", "Auto Save On Focus Out", "false"},
    {"KTextEditor Document", "Auto Reload If Any External Changes Occurs", "false"},
    {"KTextEditor Document", "Auto Reload If State Is In Version Control", "false"},
};

// command lines allowed by Kreator (not by the user in Kate)
QSet<QString> s_kreatorAllowed;
const char s_allowedKey[] = "AllowedServerCommandLines";
const char s_blockedKey[] = "BlockedServerCommandLines";

bool separateFiles(const KSharedConfig::Ptr &ours, const KSharedConfig::Ptr &kate)
{
    return QFileInfo(ours->name()).fileName() != QFileInfo(kate->name()).fileName();
}
}

QStringList SharedSettings::editorGroups()
{
    return {QStringLiteral("KTextEditor Document"), QStringLiteral("KTextEditor View"), QStringLiteral("KTextEditor Renderer"),
            QStringLiteral("KTextEditor Editor")};
}

void SharedSettings::importFromKate(const QStringList &groups)
{
    static QSet<QString> done;
    KSharedConfig::Ptr ours = KSharedConfig::openConfig();   // <app>rc, read by KTextEditor and the plugins
    KSharedConfig::Ptr kate = KSharedConfig::openConfig(QStringLiteral("katerc"));
    if (!separateFiles(ours, kate))
        return;
    for (const QString &name : groups) {
        if (done.contains(name))
            continue;
        done.insert(name);
        KConfigGroup src(kate, name);
        KConfigGroup dst(ours, name);
        if (src.exists()) {
            dst.deleteGroup();
            src.copyTo(&dst);
        }
        for (const Override &o : s_overrides) {
            if (name == QLatin1String(o.group))
                dst.writeEntry(o.key, QString::fromLatin1(o.value));
        }
    }
    ours->sync();
}

void SharedSettings::exportToKate(const QStringList &groups)
{
    KSharedConfig::Ptr ours = KSharedConfig::openConfig();
    ours->sync();
    KSharedConfig::Ptr kate = KSharedConfig::openConfig(QStringLiteral("katerc"));
    kate->reparseConfiguration();
    if (!separateFiles(ours, kate))
        return;
    for (const QString &name : groups) {
        KConfigGroup src(ours, name);
        if (!src.exists())
            continue;
        KConfigGroup dst(kate, name);
        // Kate keeps its own values of Kreator's overrides
        QList<std::pair<const char *, QString>> kept;
        QList<const char *> absent;
        for (const Override &o : s_overrides) {
            if (name != QLatin1String(o.group))
                continue;
            if (dst.hasKey(o.key))
                kept.append({o.key, dst.readEntry(o.key, QString())});
            else
                absent.append(o.key);
        }
        const QStringList kateAllowed = dst.readEntry(s_allowedKey, QStringList());
        dst.deleteGroup();
        src.copyTo(&dst);
        if (name == QLatin1String("lspclient") && dst.hasKey(s_allowedKey)) {
            QStringList allowed = dst.readEntry(s_allowedKey, QStringList());
            allowed.removeIf([&](const QString &c) {
                return s_kreatorAllowed.contains(c) && !kateAllowed.contains(c);
            });
            dst.writeEntry(s_allowedKey, allowed);
        }
        for (const auto &[key, value] : kept)
            dst.writeEntry(key, value);
        for (const char *key : absent)
            dst.deleteEntry(key);
    }
    kate->sync();
}

void SharedSettings::shareLanguageServerSettings()
{
    // the LSP client reads <app config dir>/lspclient/settings.json; Kate's is
    // ~/.config/kate/lspclient/settings.json: use that one (a link)
    const QString kateFile = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)
        + QStringLiteral("/kate/lspclient/settings.json");
    const QString ourDir = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation) + QStringLiteral("/lspclient");
    const QString ourFile = ourDir + QStringLiteral("/settings.json");
    const QFileInfo ourInfo(ourFile);
    if (ourInfo.exists() || ourInfo.isSymLink() || !QFileInfo::exists(kateFile))
        return;
    QDir().mkpath(ourDir);
    QFile::link(kateFile, ourFile);
}

void SharedSettings::allowServerCommand(const QStringList &cmdline)
{
    if (cmdline.isEmpty())
        return;
    const QString line = cmdline.join(QLatin1Char(' '));
    KSharedConfig::Ptr ours = KSharedConfig::openConfig();
    KConfigGroup group(ours, QStringLiteral("lspclient"));
    QStringList allowed = group.readEntry(s_allowedKey, QStringList());
    // (one the user blocked in Kate stays blocked)
    if (allowed.contains(line) || group.readEntry(s_blockedKey, QStringList()).contains(line))
        return;
    allowed.append(line);
    s_kreatorAllowed.insert(line);
    group.writeEntry(s_allowedKey, allowed);
    ours->sync();
}
