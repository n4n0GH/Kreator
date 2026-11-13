// Kate's settings, shared with Kreator.
//
// KTextEditor and Kate's plugins keep their settings in the application's own
// config file (kreatorrc). Kate's groups are copied from katerc before the
// editor / a plugin is created, and written back to katerc whenever they are
// changed in Kreator. A few document settings are Kreator's own and never
// written back: Kreator, not Kate, saves its files (no swap files, auto save
// or auto reload of the documents it shows).

#pragma once

#include <QStringList>

namespace SharedSettings
{
// Kate's editor groups
QStringList editorGroups();
// copy these groups katerc -> kreatorrc (once per group per process)
void importFromKate(const QStringList &groups);
// copy these groups kreatorrc -> katerc
void exportToKate(const QStringList &groups);
// Kate's LSP client settings file (settings.json) for Kreator too
void shareLanguageServerSettings();
// Kreator's language server (its own setting) may start without Kate asking
// first; allowed in kreatorrc only, Kate's allow list stays Kate's
void allowServerCommand(const QStringList &cmdline);
}
