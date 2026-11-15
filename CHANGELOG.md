# Changelog

## Unreleased

- **Component previews in the Add tab:** pointing at a component, or going
  through the list with the arrow keys, shows it beside the sidebar before
  it is added: the live component with its full description, as in Kirigami
  Gallery. Empty containers are shown with example contents, pages in a
  window, dialogs open; a form's widgets as pictures. *Show Previews* beside
  the search field switches them off.
- The Add tab's list can be used with the keyboard: Down from the search
  field, the arrow keys, Enter or Space to add.
- Fixed: previewing a file of a QML module could replace the `qmldir` in the
  module's build folder (or one next to the file) with the one Kreator
  writes for its stand-in of the module.

## 0.1.0

The first release.

- **Design view** for Qt Quick / Kirigami (`.qml`) files and Qt Designer
  (`.ui`) forms: a live preview, selecting objects in it or in the outline, a
  property inspector with an editor per type, and a component palette that
  follows the KDE Human Interface Guidelines.
- **Building a user interface from nothing:** *New Project…* creates a
  folder with a first file. Components go among an object's contents or into
  its `header`, `footer`, `contentItem`, `delegate` and other properties
  that hold objects; properties can be declared in the properties panel;
  models, `Connections` and `Settings` are in the palette. `examples/tasks`
  is a to-do application built this way.
- **Run** starts the application on its own with `qml6` and collects what it
  prints.
- **Design grid** in Kirigami units, with snapping, alignment guides and
  distance indicators.
- **Source view** with Kate's editor (KTextEditor) and its LSP client, or a
  built-in editor; both use Qt's `qmlls`.
- **Signal flow** view: a graph of which objects make which others do
  something; a form's connections can be edited in it.
- **Guidelines:** KDE HIG checks with one-click fixes, and qmllint's
  findings for the whole project with quick fixes.
- **Projects, tabs and sessions:** a folder's files in the sidebar, tabbed
  documents that keep unsaved changes and undo history, also across
  restarts.
