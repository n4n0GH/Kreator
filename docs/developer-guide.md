# Kreator developer guide

How Kreator is put together, where things live, and how to change it. For
what Kreator does from a user's point of view, see the
[user guide](user-guide.md).

- [Overview](#overview)
- [Getting set up](#getting-set-up)
- [Source layout](#source-layout)
- [The document model](#the-document-model)
- [The backend](#the-backend)
- [The QML user interface](#the-qml-user-interface)
- [The preview](#the-preview)
- [The source view](#the-source-view)
- [The language server](#the-language-server)
- [Signal flow](#signal-flow)
- [Guideline checks](#guideline-checks)
- [Sessions and settings](#sessions-and-settings)
- [Testing](#testing)
- [Pitfalls](#pitfalls)
- [Common changes](#common-changes)
- [Releasing](#releasing)

---

## Overview

Kreator is a Python application (PySide6) with a Kirigami (QML) user
interface, plus one small C++ module that embeds Kate's editor.

```
                 ┌──────────────────────── Kreator process ─────────────────────────┐
                 │                                                                  │
  QML UI ───────▶│  Backend (backend.py)        LanguageSupport "Lsp" (lsp.py)      │
  (kreator/qml)  │   │ current document           │ LspClient per project root ─────┼──▶ qmlls
                 │   │ background tabs            │ project index, qmllint list     │    (one per root,
                 │   │ undo, session, project     │ RemoteSession ◀── local socket ─┼──┐  up to 3 running)
                 │   ▼                            │                                 │  │
                 │  documents.py adapters         │                                 │  │
                 │   ├ QmlAdapter → qmldoc.py     │                                 │  │
                 │   └ UiAdapter  → uidoc.py      │                                 │  │
                 │  preview.py (QML engine / QUiLoader), lint.py, signalflow.py     │  │
                 │                                                                  │  │
                 │  org.kde.kreator.kate (C++, native/kateeditor)                   │  │
                 │   KateEditor ── KTextEditor documents/views (one per tab)        │  │
                 │   KateHost   ── Kate's LSP client plugin ──▶ starts lspbridge.py ─┼──┘
                 └──────────────────────────────────────────────────────────────────┘
```

Three objects are exposed to QML as context properties (set in `app.py`):

| Name | Class | Role |
|---|---|---|
| `Backend` | `backend.Backend` | documents, editing, preview, project, session, settings |
| `Lsp` | `lsp.LanguageSupport` | qmlls: diagnostics, symbols, index, quick fixes, Kate's LSP bridge |
| `TextLayout` | `textlayout.TextLayout` | hanging indents for the built-in source editor's word wrap |

They are properties of a context of their own, in which `app.py` creates
`Main.qml` (with a `QQmlComponent`, not `engine.load()`), and not of the
engine's root context. The previews' contexts descend from the root context,
so a previewed document can't see them: an application's own `Backend` is
"not defined" in its preview, instead of being Kreator's
(`gui_preview_isolated.py`).

The C++ module adds the QML types `KateEditor` and `KateToolArea` (import
`org.kde.kreator.kate`).

---

## Getting set up

Runtime requirements are in the [user guide](user-guide.md#installing). To
develop, you also want qmlls and Kate (to work on the source view), and the
build dependencies of the native module:

```sh
# openSUSE
sudo zypper install python3-pyside6 kf6-kirigami qqc2-desktop-style \
    qt6-declarative-tools kate kf6-ktexteditor-devel qt6-declarative-devel cmake gcc-c++
```

Run from the source tree with `./kreator.sh` (it sets `PYTHONPATH` and runs
`python3 -m kreator`).

### The native module

`kreator/native.py` builds the C++ module the first time Kreator starts, and
again whenever a file in `kreator/native/kateeditor/` is newer than the built
plugin. The build goes to `kreator/native/build/`, and the QML module ends up
in `kreator/native/build/qml/org/kde/kreator/kate/`. To build by hand, for
example to see compiler errors:

```sh
cmake -S kreator/native/kateeditor -B kreator/native/build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build kreator/native/build -j"$(nproc)"
```

The module links the system's KTextEditor dynamically, and loads Kate's LSP
client plugin from Kate's installation at run time, so updates of either reach
Kreator without a rebuild. If the build fails, Kreator prints why and falls
back to its built-in source editor.

`kreator/native/kateeditor/demo/` is the original prototype: a minimal
Kirigami window with the editor, useful to try things in isolation.

---

## Source layout

```
kreator.sh                 run from the source tree
tools/release.sh           make a release (see Releasing)
CHANGELOG.md               what changed, per version
pyproject.toml             packaging (pip install --user --no-deps .)
examples/                  a Kirigami settings page and a Designer form to try things on;
                           tasks/: an application built in Kreator (see gui_tutorial_project.py)
tests/                     unit tests (see Testing)
docs/                      this guide and the user guide
kreator/
  app.py                   entry point: arguments, Qt setup, wiring, start/quit
  backend.py               Backend: the QObject behind the whole UI
  documents.py             QmlAdapter / UiAdapter: one editing interface for both formats
  qmldoc.py                round-trip QML parser and serialiser
  uidoc.py                 Qt Designer .ui model on ElementTree
  preview.py               live previews (QML engine, QUiLoader), hit testing, plugin preloading
  mocks.py                 stand-ins for QML modules compiled into an application
  palette.py               components of the Add tab
  lint.py                  KDE HIG checks and their fixes
  signalflow.py            signal flow analysis and graph layout
  lsp.py                   qmlls client, sharing with Kate, project index
  lspbridge.py             tiny pipe Kate's LSP client starts instead of a server
  typeinfo.py              descriptions of C++ QML types from .qmltypes files
  runner.py                Run: the application as a process of its own (qml6), its output
  project.py               folder scanning and fuzzy matching for the Files tab / Quick Open;
                           new projects (templates, creating the folder)
  session.py               compact undo history for the saved session
  editors.py               external editors (Kate, custom), settings defaults
  katestyle.py             Kate theme / settings for the built-in source editor
  semantic.py              QML and XML highlighters with semantic tokens (built-in editor)
  textlayout.py            hanging-indent word wrap (built-in editor)
  models.py                RowsModel: list model with incremental updates
  native.py                builds / finds the C++ module
  native/kateeditor/       the C++ module (KateEditor, KateHost, …)
  qml/                     the user interface
```

---

## The document model

Kreator edits files **without losing anything it doesn't understand**. Users
open real projects in it, and a save must not reformat or drop code they
didn't touch.

### QML: `qmldoc.py`

A hand-written tokenizer and parser that understands QML's declarative
structure:

- objects
- bindings, including grouped (`anchors { … }`) and attached (`Layout.fillWidth`)
- property declarations
- inline components
- `Behavior on x {}` value sources

Everything it doesn't need to edit (functions, signals, enums, JavaScript
expressions, comments) is kept as verbatim text.

- `parse(text)` returns a `QmlDocument` with a tree of `ObjectNode`s. Their
  members are `Binding`, `PropertyDecl`, `GroupNode`, `RawMember` (verbatim
  functions, signals, …) and child `ObjectNode`s.
- Every node has a `uid`, an integer that identifies it for the lifetime of
  the parsed document. The UI refers to objects only by uid.
- Members remember their source `line` and `column`, for jumping from the
  design and signal flow views to the code.
- `QmlDocument.to_text()` serialises. Untouched code keeps its formatting;
  comments are attached to the member that follows them.

`tests/test_qml_roundtrip.py` parses and re-serialises every QML file found on
the system and checks the result means the same. Run it after changing the
parser.

### Qt Designer forms: `uidoc.py`

`UiDocument` wraps an ElementTree of the `.ui` XML. `UiNode` represents a
widget, layout, spacer or action; it is also identified by `uid`. The model
covers properties, layout items (grid rows and columns), signal/slot
connections, and the signals and slots a form declares for its own class or
custom widgets.

### One interface: `documents.py`

`QmlAdapter` and `UiAdapter` give the backend the same interface for both
formats: `outline()`, `properties()`, `set_property()`, `remove_property()`,
`set_id()`, `set_type()`, `insert()`, `delete()`, `move()`, `copy_text()`,
`paste()`, `duplicate()`, `lint()`, `apply_fix()` and `text()`. They raise
`EditError` for edits that can't be made. `open_document(text, path)` picks
the adapter.

Format-specific operations exist only on one adapter: `remove_member()`,
`slots()` and `declare_property()` (QML), and the connection methods and
`remove_declared()` (forms).

### Where an inserted component goes (QML)

`QmlAdapter.insert(uid, entry, slot="", slot_is_list=False)` adds a palette
entry to an object:

- **Without a slot**, `_place()` decides, as before: an entry's own `slot`
  (actions, a window's page or drawer), a sibling after a leaf control
  (`LEAF_TYPES`), else a child. Before that, `_content_target()` sends what
  is drawn (entries without `visual=False`) from a Kirigami window to its
  declared `pageStack.initialPage`: children of the window itself would
  cover the page stack. `container_for()`, which drops use, does the same.
- **With a slot** (the Add tab's *Add to*), `_place_in_slot()` assigns the
  object to that property of the selected object: it appends to a list,
  turns a single object of a list property into a list, and refuses a
  property that already holds its one object or is set by an expression.

`QmlAdapter.slots(uid, live)` lists the properties to offer. They are the
names in `SLOT_PROPERTIES` that the **live object** has as a writable object
property (or a list property), plus `pageStack.initialPage` for a Kirigami
window. What a type has is remembered per type name (`_slots_of_type`), for
the moments without a live object (right after an edit, or when the preview
fails); a type never seen only offers what the object already uses. To offer
another property, add its name to `SLOT_PROPERTIES`.

`Backend.insertSlots` / `insertSlot` expose this to the Add tab;
`insertSlot` goes back to "" (the contents) with every selection change, so
a choice applies to one insertion.

Two more things arrive through `set_property()`, from the fields at the
bottom of the properties panel:

- A name that is a declaration (`property int count`, `required property
  string title`; `_DECLARATION`) calls `declare_property()`.
- An expression that is an object or a list of objects (`QQC2.ToolBar {}`)
  is stored as nodes (`qmldoc.parse_value_objects()`), so it is in the
  outline at once, with unique ids.

A `ListElement` can't have an id (the palette entry says `id=False`), and
its values can't be script: `encode()` never wraps them in a translation
call, and the lint doesn't ask for one.

---

## The backend

`backend.Backend` holds the application state and exposes it to QML through
properties, signals and slots.

### Documents

- The **current document** lives in fields on the backend:
  - `adapter`, `path` and `saved_text`
  - `undo_stack` and `redo_stack`
  - `selected` (a uid), `collapsed`, and so on
- Every **other open tab** is a `DocState` in `self.docs`, with the same data.
  `switchTo()` stashes the current one into `docs` (`_stash()`) and activates
  the target (`_activate()`).
- `tab_order` is the order of the tabs. Keys are file paths, or `untitled:N`.

### Editing and undo

Every change goes through `Backend._edit(fn, *args)`:

1. It remembers the document text and the selection (as a preorder index).
2. It runs the adapter call.
3. If the adapter raised, it restores the document.
4. If the text changed, it pushes an undo snapshot (the full text, at most 200
   per document) and calls `_after_change()`.

Undo and redo swap full-text snapshots and reparse. This is simple and robust:
any change can be undone, whatever made it.

`_after_change()` refreshes everything that depends on the document: the lint
issues, the outline, palette, issues and properties models, and the preview.
It emits `contentChanged`, `stateChanged` and `documentsChanged`.

Text from outside the adapters is applied as a whole new text:

- `applySource()` takes the source view's edits.
- `apply_text_fix()` takes quick fixes, possibly for a file that isn't open:
  it opens it as a background tab.
- `_reload_from_disk()` takes external changes.

### Signals

| Signal | Emitted when |
|---|---|
| `documentChanged` | another document is shown (or none) |
| `contentChanged` | the current document's text or structure changed |
| `selectionChanged` | the selected object changed |
| `stateChanged` | modified flag, undo/redo availability |
| `documentsChanged` | the set of open documents or their modified flags |
| `previewChanged`, `noteChanged` | the preview object, errors or notices |
| `projectChanged` | a folder was opened or closed, or its files changed |
| `diskChanged` | the file changed on disk (`externalChange`, `externalError`) |
| `editorsChanged` | settings changed (also restarts qmlls) |

### Models

### Projects

A project is a folder; opening one is `openFolder()`. *New Project…*
(`NewProjectDialog.qml`) asks `projectProblem()` while the user types and
calls `createProject(name, location, template)`: `project.create_project()`
makes the folder and writes the template's file (`PROJECT_TEMPLATES`, never
over an existing file), then the folder and the file are opened. The folder
it was created in is remembered as the `projectLocation` setting.

The QML templates use `qsTr()`: a new project is run with `qml6 Main.qml`,
where `i18n()` doesn't exist. `QmlAdapter.tr_fn()` then keeps using `qsTr()`
for inserted components.

### Run

`runner.Runner` starts a QML file with Qt's `qml` runtime
(`find_qml_runtime()`) in a `QProcess`, one at a time, with the file's
folder as working directory and Kreator's `-I` import paths. It collects the
merged output (`QT_FORCE_STDERR_LOGGING=1`: without a terminal Qt would log
to the journal), emits `problemReported` for the first line of a run that
tells of a problem (`problem_in()`), and `finished(name, code, failed)`; a
run that was stopped is not a failure.

The backend decides what to run (`_run_target()`: the project's `Main.qml` /
`main.qml` while a document of the project is shown, else the shown QML
document) and saves the modified documents in that file's folder first
(`_save_documents()`, which `saveAll()` uses too). `Backend.shutdown()` stops
the process. In QML, `Main.qml`'s `runApplication()` applies source edits
and gives an untitled document a file before calling `Backend.run()`, and
turns `runProblem` / `runFinished` into notifications; `RunOutputDialog.qml`
shows `Backend.runOutput`. The shortcut is in `releasedShortcuts` of
`KateSourcePane.qml`.

### Models

Lists shown in QML are `models.RowsModel` instances:

- the outline, properties, palette and issues of the current document
- the project's files (`_project_model`)
- the document tabs (`_tabs_model`)

`set_rows()` diffs the old and new rows by a key column and emits row
inserts, removes and `dataChanged`, so delegates and scroll positions survive
updates.

---

## The QML user interface

All QML is in `kreator/qml/`. `Main.qml` is the window: dialogs,
save/discard logic, the periodic session save. `EditorPage.qml` is the one
page: its toolbar actions, the sidebar / main area / properties layout, and
the global shortcuts.

| File | What it is |
|---|---|
| `SidePanel.qml` | the sidebar's tabs: Files (`ProjectPanel`), Outline / Symbols (`SymbolsView`), Add, Guidelines (`IssuesPanel` + `ProjectLintView`) |
| `ComponentPreview.qml` | what a component of the Add tab looks like, shown beside the sidebar |
| `DocumentTabs.qml` | the tab bar |
| `PreviewPane.qml` | the design view: preview, selection overlay, design grid, preview toolbar |
| `PropertyPanel.qml`, `PropertyRow.qml` | the properties panel and its per-type editors |
| `KateSourcePane.qml` | the source view with Kate's editor |
| `SourcePane.qml` | the built-in source editor (fallback), with `CompletionPopup`, `SearchBar`, `GotoLineBar`, `RenameBar`, `ReferencesPanel` |
| `FlowPane.qml`, `ConnectionDialog.qml` | the signal flow view and the form connection dialog |
| `EditorSettingsPage.qml` | *Configure Kreator…* |
| `QuickPicker.qml` | Quick Open and Go to Symbol |
| `TypeInfoPopup.qml` | the description of a C++ type (go to definition) |
| `IndexStatus.qml` | indexing progress at the bottom of the sidebar |
| `WelcomeView.qml` | the welcome screen |
| `NewProjectDialog.qml` | *New Project…* |
| `RunOutputDialog.qml` | *Run Output…* |
| `PaneSplitView.qml` | a SplitView whose handles only take clicks on their own side |

`EditorPage` loads `KateSourcePane.qml` by URL, and only when
`Backend.kateEditorAvailable` is true, because that file imports the native
module. Both source panes have the same interface: `active`, `load()`,
`commitPending()`, `pendingText()`, `gotoPosition()` and `currentLine`.

#### The Add tab's previews

`ComponentPreview.qml` is an item in the window's overlay, placed beside the
sidebar and level with the row it is shown for. `SidePanel.qml` tells it the
row: the one the pointer is on, or the list's current one when the arrow
keys came last. It asks `Backend.componentPreview(index, stage)` what to
show:

- **QML:** `palette.preview_qml(entry)` wraps the entry's snippet (or its
  `demo`) in a stage item, and `QmlPreview.demo_item()` creates it as a
  child of the preview's stage, in a context of its own like the design
  view's previews (so `Backend` isn't visible to it). The components are the
  real ones, in Kreator's own style and colours. The compiled demos are kept;
  the item lives until the next preview or `clearComponentPreview()`.
- **Forms:** `UiPreview.demo_image()` builds the widget with example
  contents and grabs it; the picture is served as `image://kreatorpalette/…`.
- **Nothing to draw:** the preview shows the entry's icon and a note.

What keeps a preview from getting in the user's way:

- The stage is a `FocusScope` that never has the focus, and a dialog's demo
  sets `focus: false`: typing in the search field goes on. A `MouseArea`
  over the stage takes what the pointer does.
- A dialog is opened with `popupType: Popup.Item`, not modal, with the stage
  as its parent, so Qt draws it over the stage (in the window's overlay,
  like the preview) and it blocks nothing.
- Demo files are named `.kreator-palette-<name>.qml`, not
  `.kreator-preview-…`: their warnings aren't reported as the document's.
- Drawers can't be shown: Qt attaches them to the window's edge. The
  `GlobalDrawer` entry is a sketch made of delegates, and says so in its
  note.

The UI follows the KDE HIG, like what Kreator checks: Kirigami units for
spacing, title case for actions and buttons, sentence case for labels,
an ellipsis (`…`) for actions that open a dialog.

---

## The preview

### QML documents

`QmlPreview.create()` in `preview.py` builds the preview:

1. `build_preview_document()` deep-copies the document and adapts it for
   embedding:
   - Windows become items: `Kirigami.ApplicationWindow` becomes
     `ApplicationItem`, a Qt Quick Controls `ApplicationWindow` becomes a
     `Page`, and the declared size is kept as the implicit size.
   - Every object gets `objectName: "__qv_<uid>"`, a marker that maps live
     objects back to document nodes. `find_named()` collects them,
     `pick_stack()` lists the objects under a point, topmost first
     (`pick_item()` takes the top one). `Backend.pressAt()` uses it: it
     keeps a covered selection selected so it can be dragged (a click
     without dragging then selects the top one), and with Alt selects the
     next one down. Forms use `UiPreview.pick_stack()`.
2. The text is loaded as a `QQmlComponent` next to the document's file, so
   relative imports work. The context object is `I18nShim`, which provides
   `i18n()` and friends.
3. If creating it fails, Kreator retries, up to 16 times:
   - Bindings named in the errors are stripped (`_strippable()`), and the
     notice lists them.
   - Imports of application-internal modules are replaced by stand-ins from
     `mocks.py`. Their QML files come from the source tree, and their C++
     types become stub objects built from the build's `plugin.qmltypes`.

A document that is itself a file of such a module uses the module's types
without importing it, which from the source folder only works for the QML
files next to it. `mocks.own_module()` finds the module by the build `qmldir`
that lists the document, looking below the project's folder (the one with
`.git`, else the outermost with a `CMakeLists.txt`, `Cargo.toml` or
`meson.build`; the scan is kept for ten seconds). The stand-in is built the
same way, plus the folder's files the build doesn't list yet, and
`_with_import()` adds the import to the preview's text on the line of its
first import (`gui_preview_own_module.py`).

The live objects also give the property panel its runtime values (`= 320`).
`Backend._live` maps uids to them as they were when the preview was created.
Objects made later, such as a view's delegates (made once the view is laid
out), are looked up when asked for (`_live_object()`): the first instance
stands for the object, for *Show All Properties* and for the Add tab's
*Add to* list.

`backend.previewShown` tells the backend whether the preview is on screen.
While the source or flow view is shown, the preview is built a moment after a
tab switch instead of during it.

**Lifetime:** each preview's `QQmlComponent` and `QQmlContext` are made
children of the object they created. PySide ties a created object's wrapper
to its component's wrapper, so dropping the component invalidates the
object's wrapper, and the backend could then neither hide nor delete the
replaced preview (`_set_preview()`, `_bury()`).

**Popups:** Qt moves a popup's visual item into the overlay of its window
when it opens, and Kirigami puts more there (drawers, passive notifications).
The preview is in Kreator's window, so an application's sidebar would cover
Kreator's own, and its modal dialogs dim and block all of Kreator.
`PopupConfiner` (`preview.py`) watches the overlay and hands everything in it
that belongs to a preview (told by its QObject and item parents) to
`popupLayer` in `PreviewPane.qml`, which takes it into the frame:

- What was laid out in the overlay (`parent` or `anchors.centerIn`) is laid
  out in the layer.
- Qt places drawers by the window's size: those at the right and bottom edges
  get items that end where the window does (`rightEdge`, `bottomEdge`).
- Modal dialogs are made non-modal, and nothing dims the window. The layer's
  veil dims the frame and takes the clicks beside the dialog instead. Drawers
  stay modal: applications lay themselves out by that.
- A popup's `x` and `y` read wrong outside the overlay (Qt maps them from the
  scene). Kirigami's drawers compute their height from `y`, so that binding
  is replaced.

Qt reparents the item on every opening, so the confiner adopts it each time
(`gui_preview_popups.py`).

**`PluginPreloader`:** with PySide6 6.12, a QML plugin instantiated on the
QML loader thread can deadlock on the GIL. So every module a document imports
is loaded on the main thread first (`preload_text()` scans the imports).

### Forms

`UiPreview` renders the form with `QUiLoader` into an image, served to QML by
`UiImageProvider` as `image://kreatorui/<n>`. Clicks are mapped to widgets by
their geometry.

### The design grid

The grid lives in `PreviewPane.qml`: its settings (`Settings`, category
`designGrid`: `showGrid`, `snap`, `size`), the overlay (lines drawn in
screen coordinates above the zoomed frame, thinned out when they would be
closer than a few pixels), `selectionOverlay` (the id tag above the frame and
the eight resize handles, at screen size), `mover` (dragging the selected
object, or with `edges` set, one of its handles; it moves and resizes the live
item along for QML; `pane.align()` snaps to the lines of
`Backend.guideRects()`, the parent and its other children, before the grid,
and `pane.guidesFor()` lists the guides drawn; `pane.distancesFor()` measures
to the nearest target on each side, or to the inner edges of a target around
the object, for the `distance` indicators; `neighbourGaps()` lists the gaps
between neighbouring targets, `spacingStops()` turns them into positions with
the same gap (or midway between neighbours) for `align()`, and
`edgeStops()` into positions for a side dragged by a resize handle;
`neighbourSizes()` adds stops at the other objects' sizes when resizing (and
`nearestSize()` snaps a dropped component's size to them), and
`equalSizes()` marks the nearby objects of the same size;
`fitBetween()` stretches a dropped component between two neighbours, its size
passed to `Backend.insertComponentSized()`, and distances as
wide as one of them are marked `equal`), `nudge()` (arrow keys; Ctrl: resize; `nextStop()` picks the nearer of the
next grid line and, with the `nudgeToGuides` setting, the next guide line,
in whole pixels; `nudgeGuides` shows the result for a moment) and a `DropArea` taking
`kreator/component` drags from the Add tab (`componentDrag` in
`SidePanel.qml`, an internal drag drawn in the window overlay). While dragging, `Backend.componentSize()` gives the size the component
will likely get (QML: the snippet created in an item of the container's size
by `QmlPreview.component_size()`, cached; forms: `UiPreview.size_hint()`;
nothing for anchored, layout-filling or slot components), drawn as
`dropGhost`. The drop
rectangle aligns with `Backend.containerRects()` of the container under the
pointer, and the drop goes into that container (`insertComponentInto()`):
an aligned point can lie on a neighbour's edge.

QML snaps in design-view coordinates (the preview's top-left corner) and
hands the backend the position plus the grid's unit:

- `Backend.placementProblem(uid)`: why an object can't be placed ("" if it
  can). The adapter checks the document (root, anchors, `x`/`y` expressions,
  a form's layouts and placing containers); for QML the backend adds whether
  the live parent positions its children (`QQuickLayout`,
  `QQuickBasePositioner` in its class chain).
- `Backend.resizeProblem(uid)`: the same for sizes (`size_problem()`: root,
  anchors, `width`/`height` expressions; for QML, a `QQuickLayout` parent).
  `pane.canMove` / `canResize` cache both for the handles.
- `Backend.resizeTo(host, uid, x, y, w, h, step, unit, move)`: writes the
  size, and with `move` (a left or top handle) the position, as one edit
  (`QmlAdapter.set_geometry()`, `UiAdapter.set_geometry()`).
- `Backend.placeAt(host, uid, x, y, step, unit)`: maps the point into the
  parent's coordinates and writes it with `QmlAdapter.set_position()`
  (`position_value()`: a multiple of `Kirigami.Units.<unit>` when Kirigami is
  imported, else pixels) or `UiAdapter.set_geometry()`.
- `Backend.dropTarget()` / `insertComponentAt()`: where a dropped component
  goes. QML uses `QmlAdapter.container_for()` (leaf controls add a sibling,
  as `insert()` does) and `_content_item()` (the item declared children are
  parented to: a `Page`'s or `Flickable`'s `contentItem`); forms use
  `UiAdapter.free_container()` and `insert_free()`, sized by
  `UiPreview.size_hint()`. Inserting and positioning are one undo step.

After placing, the preview is rebuilt at once (`_placed()`), not after the
usual delay, so the next arrow key starts from the new position. Before
hit-testing, a preview that is due is rebuilt first (`_fresh_preview()`):
undo and source edits make the document's objects anew, with new uids, and
the shown preview still maps the old ones.

---

## The source view

### Kate's editor: `native/kateeditor`

| Class | Role |
|---|---|
| `NativeWidgetItem` | Shows a QWidget in the QML scene: the widget becomes a native child window of the QQuickWindow (a subsurface on Wayland) and is kept over the item. Native windows are always on top, so while a QML popup overlaps it the item shows a snapshot instead ("frozen"). It also gives Kate's own popups Kreator's window as transient parent. |
| `KateEditor` | The editor item. It keeps **one KTextEditor document and view per Kreator document** (`documentKey`; others are dropped when they leave `openKeys`). The views are stacked in one container widget, so switching tabs only changes the visible view. Kreator's text is set with `text`; edits come back through `textEdited`. It routes keys and focus into the widget (Qt only enables Kate's editing actions in the active window, which an embedded widget never is on Wayland), and gives Kreator's shortcuts back (`releasedShortcuts`). |
| `KateHost` | Plays Kate's application and main window for plugins: the `KTextEditor::Application` / `MainWindow` relays, an XMLGUI factory for plugin actions and menus, tool views, project info. It loads Kate's LSP client plugin. Only the **shown** document counts as open for plugins. A file of another tab, or one not open, is loaded into a *side document*. Once the plugin is done, Kreator either shows the file (go to definition) or applies the change to its document (rename, code action: `fileEdited`). |
| `KateToolArea` | Kate's tool views (references, diagnostics) as a QML item. |
| `SharedSettings` | Copies Kate's editor and LSP client groups from `katerc` into `kreatorrc` before the editor exists, and back whenever they change in Kreator. Swap files, auto save and auto reload stay Kreator's own. |

Kate's LSP client never talks to qmlls directly. Kreator's project info tells
it to start `lspbridge.py` as "the server". The bridge connects to Kreator's
local socket and passes bytes through, and `lsp.py` serves it from the same
qmlls Kreator uses (see below).

### The built-in editor

`SourcePane.qml` is a `TextArea` with:

- highlighting from KSyntaxHighlighting, or `semantic.py` when semantic
  highlighting is on
- Kate's theme and settings from `katestyle.py`
- hanging-indent word wrap from `textlayout.py`
- folding, search, completion, diagnostics, references, rename and quick
  fixes, all driven by `Lsp`

It is only used when Kate's editor isn't available or is switched off.

---

## The language server

`lsp.py` has three classes:

- **`LspClient`**: JSON-RPC over one qmlls process's stdio (`QProcess`,
  non-blocking). It can serve several clients: Kreator itself through
  `request()` / `notify()`, and Kate's LSP client through `attach(session)`.
  - Requests get server-side ids of their own and are routed back.
  - Open documents are merged in `_reconcile()`: the editor's copy wins over
    Kreator's. Each server only takes the editor's documents of its own
    project root (`accepts`).
  - The server sees one version sequence per document.
- **`RemoteSession`**: one connection from `lspbridge.py`, that is, Kate's LSP
  client.
- **`LanguageSupport`** (`Lsp` in QML):
  - It owns the clients: **one per project root**, the root being the nearest
    `.qmlls.ini` or git checkout, or the open folder. The current one serves
    the shown document; up to two others stay parked (`_park()` /
    `_resume()`), so switching between projects needs no restart. A settings
    change stops all of them.
  - It handles Kreator's own requests for the shown document: diagnostics,
    symbols, completion, references, rename and code actions for the built-in
    editor, and semantic tokens.
  - It runs the **project index**. Every project file is opened in qmlls in
    turn (`_index_next()`), its symbols and qmllint diagnostics are kept in
    `_index_cache` and `_project_diags`, and a file watcher re-indexes files
    changed by other programs. Files of another root wait in
    `_index_elsewhere` until that root's server is current.
  - Then it **primes the types** (`_prime_types()`): one completion request
    inside the root object, which makes qmlls load every imported module, so
    the first real completion is fast.
  - It provides **quick fixes** for the project list. They are applied through
    `edit_handler` (`Backend.apply_text_fix`), as unsaved, undoable changes.

`app.py` wires `Backend` and `Lsp` together:

- the project's files are passed to `setProjectFiles()` on `projectChanged`
- design view edits are passed to `documentEdited()`, debounced
- `settingsChanged()` runs when the settings change

---

## Signal flow

`signalflow.py` turns a document into a graph, and `FlowPane.qml` draws it.

1. **Analysis.**
   - `ui_flow()` reads a form's `<connections>`.
   - `qml_flow()` reads QML code with the qmldoc tokenizer:
     - handlers, `Connections` and `.connect()` calls
     - function calls and emitted signals
     - bindings, split into *binding* and *layout* (anchors, sizes,
       `Layout.*`)

   Edges are keyed by `(from, fromPort, to, toPort, kind)`. A `_Graph` also
   records:
   - where each port is defined
   - which members are defined but unconnected (red ports)
   - which of those are removable
2. **Layout** (`layout()`), a layered (Sugiyama-style) layout:
   1. Back edges are found by depth-first search and reversed.
   2. Layers come from the longest path.
   3. Long edges get dummy waypoints.
   4. Nodes are ordered by barycentre.
   5. `_untangle()` sorts ports and nodes column by column in alternating
      sweeps, keeping the order with the fewest measured crossings.
3. **Drawing.** `FlowPane.qml` sizes the nodes, places them, and draws the
   edges as `Shape` paths through the waypoints. Its custom pan and zoom view
   handles mouse wheels, touchpads and pinches. Positions moved by hand are
   saved per document in the session, by a stable key: the id, or the
   object's path in the tree.

For forms, `class_members()` gets the signals and slots of Qt classes from
their meta-objects through PySide, falling back from KDE classes to the Qt
class they extend; `compatible()` checks that a slot can take a signal's
arguments.

---

## Guideline checks

`lint.py` has `lint_qml()` and `lint_ui()`, each returning issues as dicts:
`uid`, `severity`, `title`, `detail`, optional `property` and optional `fix`.
`apply_qml_fix()` and `apply_ui_fix()` apply a fix by its id. The adapters call
these through `lint()` / `apply_fix()`.

---

## Sessions and settings

- **Settings** are a `QSettings` file, `~/.config/kreator/kreator.conf`.
  Kreator's own preferences (editors, language server, session options) are
  one JSON value, `externalEditors`, read through `editors.load_settings()`.
  Its `DEFAULT_SETTINGS` lists every key with its default.
- **The session** is `~/.local/share/kreator/session.json`, written by
  `Backend.saveSession()` and read by `restoreSession()`:
  - Each document's entry has its text, saved text, disk text, pending
    source edits, signal flow positions and undo history.
  - The undo history's snapshots are stored as line diffs between neighbours
    (`session.py`), and dropped if the file changed on disk meanwhile.
  - `claimSession()` makes sure only the first running Kreator uses it.
- **Kate's settings** for the embedded editor are in `~/.config/kreatorrc`
  (see `SharedSettings`). They are copied from and written back to
  `~/.config/katerc`.
- Kreator was called QViewer before. `_migrate_from_qviewer()` in `app.py`
  takes over its settings and session once.

---

## Testing

### Unit tests

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests
python3 tests/test_qml_roundtrip.py      # every QML file on the system
```

| File | Covers |
|---|---|
| `tests/test_core.py` | parsing, serialising, editing both formats, palette insertion (also into slots) and previews, declared properties, list models, new projects, Run's output, lint and fixes, sessions, external editors |
| `tests/test_signalflow.py` | the signal flow analysis, layout, crossing reduction and member removal |
| `tests/test_qml_roundtrip.py` | the QML parser against all QML files installed on the system |

### Testing the UI

Changes to the UI should also be tried in the running application. Two ways
to do that without touching your desktop session:

- **Offscreen**, for everything but Kate's editor:
  ```sh
  QT_QPA_PLATFORM=offscreen XDG_CONFIG_HOME=/tmp/k/cfg XDG_DATA_HOME=/tmp/k/data ./kreator.sh
  ```
- **In a private, invisible KWin session**, for Kate's editor (a native
  window, which needs a real compositor):
  ```sh
  kwin_wayland --virtual --socket kreator-test --width 1500 --height 950 \
      --no-lockscreen --no-global-shortcuts \
      --exit-with-session "env WAYLAND_DISPLAY=kreator-test QT_QPA_PLATFORM=wayland ./kreator.sh"
  ```

Point `XDG_CONFIG_HOME` and `XDG_DATA_HOME` at empty folders to start from a
clean configuration and session. Put a copy of your `~/.config/katerc` there
if Kate's settings matter.

### GUI tests

`tests/gui/` holds 60 tests that drive a real Kreator: they open files,
click, type, switch tabs, restart Kreator, and check what happened.

`gui_tutorial_project.py` is the acceptance test for building a user
interface from nothing: it creates a project with *New Project…* and builds
the to-do app of the
[Kirigami Design Guide's tutorial](https://n4n0gh.github.io/Doku/tutorial/overview/)
step by step, with the operations the Add tab, the properties panel and the
outline offer (and the source view for functions). After each step the
preview must be free of errors; the finished application is then used in the
preview and run with `qml6`. `examples/tasks/Main.qml` is its result. When a
change to the palette or to where components go breaks it, a user following
the tutorial would be stuck at the same place.

```sh
tests/gui/run.py                 # all of them (about 8 minutes)
tests/gui/run.py -j 3            # three at a time (about 3 minutes)
tests/gui/run.py flow session    # those whose name contains "flow" or "session"
tests/gui/run.py -v kate_rename  # with everything Kreator prints
tests/gui/run.py --list          # the tests, and what each needs
```

- **Isolated:** each test gets a fresh temporary workspace, a copy of
  `tests/gui/fixtures/`, with its own settings and session folders. The
  source tree and your own configuration are never touched. A failed test's
  workspace is kept and its path printed, with any screenshots the test took.
- **Where they run:** offscreen, except the tests of Kate's editor (`kate_*`
  and a few others), which run in a private, invisible KWin session
  (`kwin_wayland --virtual`).
- **Skipped** when something they need is missing: KWin, qmlls, or Kate's
  editor module.
- **Mechanism:** `run.py` starts each test through `host.py`, which runs the
  test file's code inside Kreator once its window is up. The test can use
  `backend`, `lsp`, `win`, `page`, the workspace `OUT` and helpers like
  `check()` and `wait_until()`.
- **Metadata:** the first lines of a test declare what it needs, for example
  `KATE = True`, `PLAIN_EDITOR = True` (the built-in editor), `SETTINGS`,
  `NEEDS = ["qmlls"]`, or `RUNS`. A multi-run test restarts Kreator, with its
  code split by `# --- run N ---` lines. See the docstrings of `run.py` and
  `host.py` for all of it.

To add a test, copy a similar one. Each step usually ends by scheduling the
next with `QTimer.singleShot()`, so that Kreator can react in between. The
last step calls `app.quit()`. Prefer `wait_until()` to fixed delays where a
step depends on something being ready (a document open, a menu shown): the
suite also runs several tests at once, which slows each down. An uncaught
exception ends Kreator at once with exit code 2, reported as a failure.

---

## Pitfalls

**PySide6:**

- Do not use `qmlRegisterSingletonInstance()`: with PySide 6.12 it breaks
  QML type registration. Context properties are used instead.
- A slot must never return `None` for a `QObject*`.
- Python wrappers of QML objects can go stale (`RuntimeError: Internal C++
  object already deleted`, or a different object at the same address).
  Re-fetch objects rather than keeping wrappers around, especially for
  `staticMetaObject` (`signalflow._meta_object()` caches its results for this
  reason).
- `app.py` ends with `os._exit()`: PySide occasionally crashes while the
  interpreter tears down Qt objects, and everything is saved by then.
- QML plugins must be preloaded on the main thread (see
  [the preview](#the-preview)).

**Kate's editor:**

- It is a native window on top of the scene. Anything QML that has to appear
  over it must be a popup (the item freezes into a snapshot), or must leave
  room (`bottomInset`, used for notifications).
- Keys: Kreator's global shortcuts must be listed in `releasedShortcuts` in
  `KateSourcePane.qml`, or Kate's actions take them.
- Plugins must only see the shown document as open (`KateHost::findUrl`,
  `openUrl`, the app relay's `documents()`). Otherwise a rename or go to
  definition into another tab would change Kate's copy behind Kreator's
  back.

**qmlls:**

- It skips document versions it has seen before. `_next_version()` only
  counts up, also across close and reopen.
- Its `i18n()` warnings are dropped: KDE apps get `i18n()` from
  `KLocalizedContext` at run time.

---

## Common changes

### Adding a component to the Add tab

Add a `dict(...)` to `QML_COMPONENTS` (or a `_w(...)` to `UI_COMPONENTS`) in
`palette.py`.

- `cat` is the category, `desc` the description.
- `module` is the (module, alias) the component is imported from.
- `qml` is the snippet. Its placeholders are `{K}` (the Kirigami prefix),
  `{C}` (Controls), `{L}` (Layouts), `{M}` (the prefix of the entry's own
  module) and `{T}` (the translation call). Write a translated text with an
  argument as `{T}("Item %1", index + 1)`: it becomes
  `qsTr("Item %1").arg(index + 1)` in documents that use `qsTr()`.
- `slot` puts the component into a property, for example `actions`.
- `visual=False` marks what isn't drawn where it is declared (models,
  timers, dialogs): it gets no position when dropped, and stays with a
  window instead of going on its page.
- `id=False` is for objects that can't have an id (`ListElement`).

**Its preview.** The Add tab shows the snippet itself, live, beside the
sidebar (see [The Add tab's previews](#the-add-tabs-previews)). Look at the
new entry's preview: most need nothing, some need one of these keys:

- `demo` is QML shown instead of the snippet, for a component that shows
  nothing on its own: an empty layout gets `Box` placeholders, a
  `ScrollView` something to scroll. Keep it to what is added plus example
  contents, so the preview doesn't promise more than the user gets. It uses
  the same placeholders as `qml`.
- `stage` says how the component is put on the stage. The default follows
  the snippet: `"wide"` if it sets `Layout.fillWidth`, `"fill"` if it sets
  `anchors`, else `"center"` (its own size); `"none"` with `visual=False`.
  Say `"wide"` or `"fill"` for a component that only looks right with a
  width or size given to it (a delegate, a list view), `"popup"` for a
  dialog (it is opened on the stage, not modal and without focus), `"none"`
  for a visual item that draws nothing.
- `height` is the stage's height in grid units for `"fill"` and `"popup"`.
- `note` is a line below the preview, for what it can't show.

A widget's preview is drawn by `UiPreview.demo_image()` in `preview.py`: add
example contents there if the new widget is empty without them.

`BuildingTests.test_every_component_can_be_inserted` inserts every entry;
`PalettePreviewTests` and `gui_add_previews.py` (which creates every preview)
cover the previews.

Follow the HIG in the defaults.

### Adding a guideline check

Add a check to `lint_qml()` or `lint_ui()` in `lint.py` that appends
`_issue(node, title, detail, severity, prop, fix)`. For an automatic fix, give
it a fix id and handle that id in `apply_qml_fix()` / `apply_ui_fix()`. Add a
test to `tests/test_core.py`.

### Adding a setting

1. Add the key and its default to `DEFAULT_SETTINGS` in `editors.py`.
2. Let `load_settings()` copy it.
3. Read it in Python with `Backend._editor_settings()`.
4. Add the control to `EditorSettingsPage.qml`, which writes it with
   `page.cfg.<key> = …; page.commit(…)`.

`editorsChanged` is emitted after a change, and `Lsp.settingsChanged()`
restarts qmlls.

### Adding a backend operation that edits the document

1. Implement it on the adapter (`documents.py`), raising `EditError` for
   invalid input.
2. Add a `@Slot` on `Backend` that calls `self._edit(self.adapter.method,
   …)`. Undo, the models, the preview, the session and the qmllint list then
   follow by themselves.

---

## Releasing

1. Set the version in `kreator/__init__.py` and `pyproject.toml`.
2. Describe it in `CHANGELOG.md`, under `## <version>`.
3. Commit, on `main`.
4. Run `tools/release.sh`. It checks the above, then:
   - makes the signed tag `v<version>`
   - makes `dist/kreator-<version>.tar.gz` from the tag (`git archive`), with
     its signature (`.asc`) and checksum (`.sha256`)
   - pushes `main` and the tag
   - creates the GitHub release with the three files, and the changelog's
     section as its notes

The signing key is an OpenPGP key (Ed25519, fingerprint `33DF 82C4 E8B1
F312 C294  ECD1 664E 00DD 1520 1C7C`) in a keyring of its own,
`~/.local/share/kreator-signing` (or `KREATOR_SIGNING_HOME`), not in your
personal keyring. Its public half is `docs/signing-key.asc`. The keyring is
not part of the repository: keep a copy of the folder somewhere safe. It also
holds the key's revocation certificate (`openpgp-revocs.d/`), for the day the
key is lost or leaked.
