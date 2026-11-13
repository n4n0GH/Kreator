# Kreator user guide

Kreator is a designer for Qt user interfaces, in the spirit of Glade. It opens
**Qt Quick and Kirigami files (`.qml`)** and **Qt Designer forms (`.ui`)**,
shows them as they will look, lets you change them by clicking or by editing
the code, and checks them against the
[KDE Human Interface Guidelines](https://develop.kde.org/hig/) (HIG).

This guide walks through Kreator by task. For a compact list of every feature,
see the [README](../README.md). For how Kreator is built, see the
[developer guide](developer-guide.md).

- [1. Getting started](#1-getting-started)
- [2. The window](#2-the-window)
- [3. Designing: the design view](#3-designing-the-design-view)
- [4. Editing code: the source view](#4-editing-code-the-source-view)
- [5. Following the logic: the signal flow view](#5-following-the-logic-the-signal-flow-view)
- [6. Checking your UI: the Guidelines tab](#6-checking-your-ui-the-guidelines-tab)
- [7. Working with a project](#7-working-with-a-project)
- [8. Sessions: picking up where you left off](#8-sessions-picking-up-where-you-left-off)
- [9. Other editors](#9-other-editors)
- [10. Settings](#10-settings)
- [11. Troubleshooting](#11-troubleshooting)
- [12. Walkthrough: a to-do app from an empty project](#12-walkthrough-a-to-do-app-from-an-empty-project)
- [Keyboard shortcuts](#keyboard-shortcuts)

---

## 1. Getting started

### Installing

Kreator runs on a KDE Plasma (or any Linux) desktop with:

- Python 3.10 or newer
- PySide6 **from your distribution** (`python3-pyside6` on openSUSE and
  Fedora, `pyside6` on Arch). It has to be built against the same Qt as
  Kirigami, so the PyPI wheel does not work.
- KDE Frameworks 6: Kirigami and `qqc2-desktop-style`; Breeze icons are
  recommended.

Optional, but recommended:

- **qmlls**, Qt's QML language server (in openSUSE: `qt6-declarative-tools`):
  completion, error checking, go to definition and the project-wide qmllint
  list. The same package has **qml6**, which *Run* uses.
- **Kate**: the source view then uses Kate's own editor, including Kate's LSP
  client. Kreator compiles a small module for it the first time it starts, and
  needs `kf6-ktexteditor-devel qt6-declarative-devel cmake gcc-c++` for that.
  Without these, Kreator uses its built-in source editor.

Run it from the source folder:

```sh
./kreator.sh                              # welcome screen
./kreator.sh path/to/Main.qml             # open a file
./kreator.sh --new kirigami-app           # start from a template
./kreator.sh -I ~/src/myapp/qml Main.qml  # with an extra QML import path
```

The templates for `--new` are `kirigami-app`, `kirigami-page`, `qtquick` and
`widgets-form`. To install Kreator for your user, run
`pip install --user --no-deps .` and copy `kreator.desktop` to
`~/.local/share/applications/`.

### The welcome screen

Without a document or folder, Kreator shows the welcome screen:

- **Open a User Interface File** opens a `.qml` or `.ui` file. You can also
  drop a file onto the window.
- **New Project…** starts a user interface from nothing: it creates a folder
  with a first file and opens it, ready to add components (see
  [Creating a project](#creating-a-project)).
- **Open Folder…** opens a whole project: all of its `.qml` and `.ui` files
  are listed in the sidebar, and you can switch between them (see
  [Working with a project](#7-working-with-a-project)).
- **Or start a single file from a template**: a Kirigami application (window
  with a drawer and a page), a Kirigami page (a scrollable page with a form),
  a plain Qt Quick application, or a Qt Widgets form. These are untitled
  documents with example content, saved where you choose.
- **Recent Folders** and **Recent Files**.

### A first edit

1. Open a file, for example `examples/SettingsPage.qml`.
2. Click a control in the preview. It is selected in the preview and in the
   *Outline* tab, and its properties appear on the right.
3. Change a property, for example a label's `text`. The preview updates at
   once.
4. Press **Ctrl+Z** to undo, **Ctrl+S** to save.

---

## 2. The window

```
┌────────────────────────────────────────────────────────────────────────┐
│ Open…  Save  ↶ ↷                    Run  Source  Signal Flow  ☰        │  toolbar
├─────────────┬──────────────────────────────────────────┬───────────────┤
│ sidebar     │ [◧] Main.qml  Page.qml •  …               │ properties    │
│  Files      ├──────────────────────────────────────────┤               │
│  Outline    │                                          │  Type, id     │
│  Add        │   preview  /  source view  /  signal flow │  filter       │
│  Guidelines │                                          │  properties…  │
│             │                                          │               │
└─────────────┴──────────────────────────────────────────┴───────────────┘
```

- **Toolbar:** *Open…*, *Save*, *Undo* and *Redo* on the left; on the right
  *Run* (see [Running the application](#running-the-application)), *Source*
  (or *Design*), *Signal Flow* and the ☰ menu with everything else:
  *New Project…*, *Open Folder…*, *Quick Open…*, *Go to Symbol…*, *Open
  With*, *New*, *Run Output…*, *Open Recent*, *Save As…*, *Save All*,
  *Close Folder*, *Reload*, *Close*,
  *Configure Kreator…*, *About Kreator* and *Quit*.
- **Sidebar** (show or hide it with **F9** or the button at the start of the
  tab bar). It has four tabs:
  - **Files**: the open folder's `.qml` and `.ui` files.
  - **Outline**: the document's object tree. In the source view it becomes
    **Symbols**, the outline the language server reports.
  - **Add**: components to insert.
  - **Guidelines**: HIG checks and the project's qmllint findings.

  When the sidebar is narrow, its tabs show only their icons.
- **Document tabs**: one per open document, as in Kate. A dot marks unsaved
  changes.
- **The main area** shows one of three views of the current document:
  - the **design view**: a live preview (the default)
  - the **source view**: the code (*Source*, **Ctrl+Shift+E**)
  - the **signal flow** view: a graph of how objects drive each other
    (*Signal Flow*, **Ctrl+Shift+G**)
- **Properties panel** on the right: the selected object's type, id and
  properties.

The view you choose stays when you switch between documents.

---

## 3. Designing: the design view

### The preview

The preview is rendered by the real Qt Quick engine with the Breeze style, so
it looks like the running application:

- A Kirigami page is shown inside a page stack, with its title and toolbar
  actions.
- An `ApplicationWindow` is shown inline, at its declared size.
- What the application shows over its window, such as its sidebar, drawers
  and dialogs, stays inside the preview's frame. A modal dialog dims the
  preview, not Kreator.
- A Qt Designer form is rendered by Qt's form loader.

The preview's toolbar has:

- **Select** / **Interact**. In *Select* mode, clicking selects an object. In
  *Interact* mode you can use the preview like the real application: type into
  fields, open menus, switch pages.
- **Preview size:** *Fit to View*, *Phone (360 × 720)*, *Phone Landscape*,
  *Tablet*, *Laptop* or *Desktop*.
- **Zoom Out / Zoom In** (or **Ctrl+wheel**). Zoom also applies to previews
  of popups and dialogs.
- **Show Grid**, **Snap to Grid** and the grid's size: see
  [Placing objects on the grid](#placing-objects-on-the-grid).
- **Reload Preview.**

If the preview can't be created, the error is shown above it, with line
numbers that match the source view. Kreator keeps the last good preview
visible meanwhile. See [Troubleshooting](#11-troubleshooting) for why a
preview might differ from the real application.

### Selecting objects

Select an object by clicking it in the preview, or in the *Outline* tab. The
selection is highlighted in both. Objects without a visible area (models,
timers, actions) can be selected in the outline.

The outline's context menu (right-click, or the ⋮ button) has *Move Up*,
*Move Down*, *Duplicate*, *Cut*, *Copy*, *Paste Inside*, *Show in Kate* (or your
default editor) and *Delete*.

### Editing properties

The properties panel shows the selected object's **type** and **id** at the
top. Both can be edited:

- Changing the id also updates every reference to it in the file.
- Changing the type swaps the object's type and keeps its properties.

Below that are the properties that are set, each with an editor that fits its
type:

- switches for booleans and spin boxes for numbers
- drop-downs for enums
- a colour picker for colours
- text fields for strings. If the text is translated with `i18n()` or
  `qsTr()`, the call is kept when you edit the text.
- JavaScript expressions for bindings. Next to a binding, its current value
  in the preview is shown (`= 320`).

Each property's ⋮ menu has *Edit as Value*, *Edit as Expression*, *Copy Value*
and *Remove*.

To set a property that isn't listed, type its name and value into the fields
at the bottom of the panel and press *Add*. The value is written as you type
it, as in the code: `"Add a task"` with its quotes, `true`, `-1`,
`tasksModel.count > 0`. The same fields add:

- **a signal handler:** `onClicked` with the code to run, for example
  `root.addTask(text)`
- **an attached or grouped property:** `Layout.fillWidth`, `font.bold`,
  `Component.onCompleted`
- **an object:** `footer` with the value `QQC2.ToolBar {}`. It appears in
  the outline, where you can select and fill it. (The *Add* tab does the same
  with a click, see below.)
- **a new property of the object:** type the declaration as the name,
  `property int remaining` or `required property string title`. The value is
  optional then. The property is listed under *Declared properties*, where
  its value is edited like any other.

Turn on **Show All Properties**
to list every property of the live object, with its current value.
Kreator also suggests the attached properties that fit the object's
position: `Layout.*` inside layouts, `Kirigami.FormData.label` inside a
`Kirigami.FormLayout`.

Use **Filter properties…** to find one quickly.

### Adding components

The **Add** tab lists components to insert:

- **For QML:** Kirigami pages and content (cards, inline messages, forms, …),
  Qt Quick Controls, layouts and plain Qt Quick items.
- **For forms:** Qt Widgets.

Search with *Search components…*, then click a component to add it to the
selected object, or drag it onto the design view to add it where you drop
it. While you drag, the object it will be added to is outlined; when that
object lets its children be placed freely (an `Item`, a `Rectangle`, a
form's widget without a layout), a frame shows where the new component
goes and the size it will likely get there, and the label names it ("Add
Button to area (80 × 24)"). Its top-left corner goes on the grid point
shown, see below. In a layout, the layout places it. Components whose size
or position comes from their parent (anchored, or filling a layout) show
only the point.

The inserted code follows the HIG: spacing from `Kirigami.Units`, translated
text, and title case for button and action text. Kreator puts the component
where it belongs:

- an action goes into the page's `actions: [...]`
- a field added to a `Kirigami.FormLayout` gets a `Kirigami.FormData.label`
- a widget added to a form's grid or form layout gets a proper row and column
- a container gets a layout
- with a Kirigami window selected, what is drawn (a label, a list) goes on
  the window's page, and what isn't (a model, settings, a dialog) stays with
  the window

**Add to:** many objects have places for one particular object besides their
contents: a page has a `header` and a `footer`, a control such as a tool bar
or a list item has a `contentItem`, a list view has a `delegate`, a text
field with actions has `rightActions`. To put a component there, choose the
place under **Add to** above the component list, then click the component:

- *Its contents* (the default) adds the component among the object's
  children.
- The other entries are the properties of the selected object that hold
  objects. A property that holds one object and has one is greyed out
  ("header (has a ToolBar)"): select that object in the outline to change it,
  or delete it first. Lists such as `actions` show how many they hold, and
  take more.
- After adding, the new object is selected and the choice is back at *Its
  contents*, so you can go on filling the new object.

The **Data and Logic** group at the end of the list has objects that aren't
drawn: `ListModel` and its `ListElement`s (an element's properties are the
entry's fields; add them in the properties panel, then *Duplicate* the
element), `KSortFilterProxyModel`, `Connections` and `Settings`. Select them
in the outline.

### Placing objects on the grid

The design view has a grid to place objects on, measured in Kirigami's
units, as KDE's guidelines measure spacing and sizes. Its toolbar has:

- **Show Grid**: draws the grid over the preview. (While you move or drop
  an object with snapping on, it is shown anyway.)
- **Snap to Grid** (on by default): objects you move or drop land on the
  grid. Hold **Shift** while dragging to place an object freely.
- **Grid size** (the "8 px" menu): *Small Spacing*
  (`Kirigami.Units.smallSpacing`, 4 px), *Large Spacing* (`largeSpacing`,
  8 px, the default) or *Grid Unit* (`gridUnit`, 18 px with the default
  font). The sizes follow your font and scale settings, like the units do.
  The same menu has **Arrow Keys Stop at Guides**, see below.

**Moving an object:** in *Select* mode, drag the selected object. A frame
shows where it goes, and the preview follows. Release to place it, or press
**Escape** to cancel. With the design view focused (click it), the **arrow
keys** move the selected object to the next grid line, and **Shift+arrow**
by one pixel. With **Arrow Keys Stop at Guides** turned on (off by default),
they also stop where the object's sides or centre line up with a
neighbour's, whichever comes first, and the guide shows for a moment. This
applies to resizing with Ctrl+arrow keys too.

**Covered objects:** a click selects the object on top. To get at one
underneath, **Alt+click**: each Alt+click selects the next object under the
selected one, going round to the top again (you can also select it in the
outline). Once selected, you can drag it from anywhere inside it, even where
another object covers it; a plain click there, without dragging, still selects
the one on top. (Objects inside the selected one don't count as covering it:
pressing on them selects and drags them as usual.)

**Alignment guides:** while you move or resize an object, its sides and
centre line up with those of the objects next to it (its parent and the
parent's other children) when they come within a few pixels. An orange guide
line shows what it lines up with. A component dragged from the *Add* tab does
the same: its sides and centre (or, when its size isn't known, its top-left
corner) line up with those of the object it is dropped into and that
object's children. Alignment wins over the
grid; elsewhere the grid applies. Shift turns off both. An aligned position that isn't on the
grid is written in pixels.

**Distances:** while you move, resize or drop an object, and for a moment
after an arrow key moves it, orange measurements show how far it is from
the nearest object on each side and from the inner edges of the object
around it (within about six grid units on screen). A distance that equals
one of Kirigami's spacing units is labelled with it, e.g.
"8 · largeSpacing", so spacing that follows the HIG is easy to spot.

**Equal spacing:** when the gap between the object and a neighbour comes
within a few pixels of a gap between two other objects in the same row or
column, the object snaps to the same gap, and all equal gaps are marked
"= 22". Between two neighbours, it also snaps to the middle, with both its
gaps marked equal. This works when moving an object, when dropping a
component whose size is known, and for the side you drag when resizing: it
stops where its gap to the next object matches a gap between two others, or
the gap on the object's other side.

**Equal sizes:** when resizing, the side you drag also stops where the
object becomes as wide (or as high) as another object next to it. The
objects of that size nearby are then marked with a line along their top (or
right side), and the one you resize along its bottom (or left side),
labelled "= 80". A component you drop does the same: when its own width or
height is within a few pixels of a neighbour's, the preview takes that size
and the component gets it (the label shows its size). Filling a gap takes
precedence; Shift drops it at its own size.

**Filling a gap:** a component dragged into a gap between two objects close
by in a row (or a column) is stretched to fill it, leaving on both sides a
gap as wide as one between other objects; the preview shows the size it
gets, and dropping gives it that width (or height). Hold Shift to drop it at
its own size.

**Resizing an object:** drag one of the handles around the selected object.
The sides you drag land on grid lines (Shift: freely), and the object stays at
least one grid step wide and high. Dragging a left or top handle moves that
side, so the object's position changes too. With the design view focused,
**Ctrl+arrow keys** move the right or bottom side to the next grid line, and
**Ctrl+Shift+arrow keys** by one pixel.

The selected object's id (or type) is shown in a tag just above its frame,
outside it, so it doesn't cover the object.

In QML, a position or size on the grid is written in the grid's unit, so it scales
with the rest of the application:

```qml
x: Kirigami.Units.largeSpacing * 6
y: Kirigami.Units.largeSpacing * 4
width: Kirigami.Units.largeSpacing * 28
```

Off the grid (with Shift, or when the parent itself isn't on the grid), and
in files that don't import Kirigami, values are written in pixels. In a
form, the widget's `geometry` is set (moving keeps its size).

Only objects whose position is their own can be moved, and only those whose
size is their own can be resized; the handles show only what is possible (an
object in a `Column` can be made wider, but not moved: it gets just the right
and bottom handles). When an object can't be moved or resized, Kreator says
why while you drag it:

- its parent places it: a layout, `Row`, `Column`, `Grid`, `Flow`, or in a
  form, a layout, splitter, tab widget or similar
- it is anchored (`anchors.…`)
- its `x`, `y`, `width` or `height` is an expression (Kreator won't
  overwrite your binding)
- for resizing: a layout sizes it (use its `Layout.*` properties)
- it is the root object

In layouts, which KDE's guidelines recommend for most UIs, arrange objects
with *Move Up* / *Move Down* and the `Layout.*` properties instead.

### Changing the structure

With an object selected in the design view:

| Action | Shortcut |
|---|---|
| Delete | Del |
| Duplicate | Ctrl+D |
| Cut / Copy / Paste | Ctrl+X / Ctrl+C / Ctrl+V |
| Move up / down among its siblings | Alt+Up / Alt+Down |

Copy and paste use QML (or, for forms, XML) text. So you can paste a snippet
copied from another file or from documentation, and copy an object into a
text editor.

### Undo and redo

Every change can be undone with **Ctrl+Z** and redone with **Ctrl+Shift+Z**:
property edits, structure changes, applied source edits, quick fixes and
reloads. Each document has its own history, which is kept while you work on
other documents and, by default, across restarts (see
[Sessions](#8-sessions-picking-up-where-you-left-off)).

### Saving

**Ctrl+S** saves, **Ctrl+Shift+S** saves under a new name, and **Ctrl+L**
saves all documents. Kreator writes QML with 4-space indentation and keeps
your comments, functions, signals and the formatting of code you didn't touch.
`.ui` files are written in Qt Designer's own format.

---

## 4. Editing code: the source view

Switch to the source view with **Source** in the toolbar or **Ctrl+Shift+E**.
It shows the current document's code, with the cursor at the selected object.

### Applying your edits

The design and the code are two views of one document. Edits in the source
view are **applied** to the design:

- with **Apply** in the source view's toolbar (**Ctrl+Return**)
- when you leave the source view
- when you switch to another document

While there are unapplied edits, the toolbar says so. **Revert** throws them
away. If the code doesn't parse, Kreator tells you and stays in the source
view until you fix or revert it. Unapplied edits are kept even if Kreator
crashes, and come back on the next start.

### Kate's editor

When Kate is installed (see [Installing](#installing)), the source view **is
Kate's editor**: the same component Kate uses, from your system. Everything
works as in Kate:

- highlighting, folding, multiple cursors, vi mode, spell checking, the
  minimap
- search and replace (**Ctrl+F** / **Ctrl+R**) and go to line (**Ctrl+G**)
- **Ctrl+Z** in the source view is Kate's undo for your typing. Kreator's
  undo takes over again once the edits are applied.

**Settings are shared with Kate.** Kreator starts with Kate's editor settings
(colour theme, font, indentation and so on). **Configure Editor…** in the
source view's toolbar opens Kate's settings pages, and changes made there are
written back to Kate. A few settings are Kreator's own: Kreator saves its files
itself, so Kate's swap files, auto save and auto reload are off here.

**Each tab has its own editor document**, as in Kate. Switching back to a tab
keeps its cursor, scroll position and editor undo history.

Some keys belong to Kreator rather than the editor, so they work the same
everywhere:

- Ctrl+S and Ctrl+Shift+S (save)
- F5 (reload)
- Ctrl+Return (apply)
- Ctrl+Shift+E (design or source)
- Ctrl+Shift+G (signal flow)
- Ctrl+Shift+R (run)
- Ctrl+Shift+O (open in your external editor)
- Ctrl+Alt+P (go to symbol)

### Language features

With qmlls available, Kate's LSP client runs in the editor, using Kreator's
qmlls. You get:

- **completion** as you type
- **diagnostics**: problems are underlined, with details on hover. The
  problem counter in the toolbar jumps to the next one when clicked.
- **go to definition** (Ctrl+click). In another QML or UI file, that file
  opens in Kreator. For a type implemented in C++ (`Rectangle`, `Item`,
  `Kirigami.Icon`, …), which has no source file, Kreator shows a short
  description instead: its module, properties, signals and methods, with
  inherited members grouped by base type.
- **find references**, **rename** (F2) and **code actions** (Alt+Return).
  You can find all of these in the editor's context menu. A rename or code
  action that changes other files changes them in Kreator as unsaved, undoable
  edits; nothing is written to disk until you save.
- **Panels** in the toolbar shows Kate's panels below the editor: the
  references list and Kate's diagnostics list.

A project's `.qmlls.ini` file is respected. It tells qmlls where the build
directory and import paths are, so modules that only exist in your
application's build (for example a cxx-qt or CMake QML module) are understood
too.

### Symbols and Go to Symbol

In the source view, the sidebar's *Outline* tab becomes **Symbols**: the
objects (with their ids), properties, functions and signals of the file, as
qmlls reports them. It follows the cursor and jumps to a symbol when you click
it. *Show Property Bindings* (the button next to the filter field) also lists
property bindings, and the field filters the list.

**Go to Symbol** (**Ctrl+Alt+P**) is a quick search over the same symbols.

### The built-in editor

Without Kate's editor (it isn't installed, or *Use Kate's editor* is switched
off in the settings), Kreator uses its own source editor. It follows your Kate
settings in `katerc` too (theme, font, indentation, word wrap, bracket
matching), and offers search and replace, go to line, folding, completion,
diagnostics, go to definition (F12), find references (Shift+F12), rename (F2),
quick fixes (Alt+Return) and semantic highlighting.

---

## 5. Following the logic: the signal flow view

**Signal Flow** in the toolbar (**Ctrl+Shift+G**) shows a graph of which
objects make which others do something. It is read left to right.

### Reading the graph

Each object is a box (node) with **ports**: the signals, functions and
properties that take part.

- An **output** port has its connector on the right, and an **input** port on
  the left. A function has both sides: who calls it, and what its body does.
- **Arrows** run from port to port. In a dialog with
  `onOpened: nameField.forceActiveFocus()`, an arrow goes from the dialog's
  `opened` port to the `forceActiveFocus()` port of `nameField`.
- **Solid** arrows are signals and the code that handles them, **dashed**
  arrows are bindings to other objects' properties, and **dotted** arrows are
  layout bindings (anchors, sizes, `Layout.*`).
- Objects outside the file (for example a `Connections` target that comes
  from C++) are grey boxes marked *outside this file*.
- A **red** port is defined in the file but nothing in the file connects to
  it: a function nobody calls, a signal nobody emits or handles, a declared
  property nobody reads or sets. It may still be used from another file.
  The port's tooltip explains which case it is.

Kreator orders ports and objects so that as few arrows as possible cross.

The toolbar filters what is shown:

- **Signals**, **Bindings** and **Layout** turn kinds of arrows on and off.
  Layout is off by default.
- **Selected Object Only** shows only what the selected object is connected
  to. A document with more than 150 arrows starts this way; **Show All** shows
  everything.

For a QML file, the graph is found by reading the code: signal handlers,
`Connections` blocks, `x.signal.connect(f)` calls, function calls and
emitted signals, and bindings. It only sees what the code names by id; what
goes through JavaScript variables, models or C++ isn't drawn. For a Qt
Designer form, the graph shows the form's signal/slot connections, which is
exact.

### Getting around

- **Hover** the dot in the middle of an arrow to see what it does and where.
  **Click** it to open that code in the source view.
- **Click a port** to see where it is written, or where it is used.
- **Click an object** to select it, and its arrows stand out. **Double-click**
  it to see its code.
- **Drag an object's title bar** to move it. Moved objects keep their places,
  also across restarts, until you click **Reset Layout**.
- **Zoom** with the mouse wheel or a touchpad pinch (or Ctrl + two-finger
  scrolling), at the pointer. **Scroll** with two fingers on a touchpad, or by
  dragging the background. *Fit to View* shows the whole graph.

### Removing unused members

Click a red port that is a declaration (a function, a signal or a property;
in a form, a declared signal or slot) and choose **Remove**. It is deleted
with its comments, as an ordinary undoable change. A red signal handler can't
be removed this way, because its code may still do something the graph doesn't
show.

### Editing a form's connections

For a Qt Designer form, the connections can be edited right in the graph:

- **Drag** from a signal's connector, or from the handle on a widget's title
  bar, to another widget. Drop onto one of its slots to pick that slot too. A
  dialog opens to confirm or complete the connection.
- **New Connection…** in the toolbar does the same without dragging.
- **All Widgets** also shows the widgets that have no connections yet, so you
  can connect them.
- **Click an arrow's dot** to *Edit Connection…*, *Delete Connection* or
  *Show in Source*.

The connection dialog lists the signals and slots of the widgets' classes:
Qt's own, those the form declares, and for custom or KDE widgets those of the
class they extend. Only slots that can take the signal's arguments are listed.
You can also type a signature, for example a slot that only exists in your
C++ code.

---

## 6. Checking your UI: the Guidelines tab

The **Guidelines** tab has two lists.

### KDE HIG

The **KDE HIG** list checks the current document against the KDE Human
Interface Guidelines and Kirigami best practices. It reports, for example:

- untranslated text
- hard-coded spacing, sizes, colours and font sizes (use `Kirigami.Units` and
  the theme instead)
- `Text` used where `Label` belongs
- button and action text that isn't in Title Case
- form labels without a colon, and check box text with one
- three dots instead of an ellipsis (`…`)
- icon-only buttons without text (screen readers need the text)
- pages without a title, and an `ApplicationWindow` that isn't Kirigami's
- in forms: style sheets, labels without a buddy, fixed sizes and hard-coded
  layout spacing

Click an issue to select the object. Most issues have a **Fix** button, and
**Fix All** applies every automatic fix. Fixes are ordinary undoable changes.

### qmllint

The **qmllint** list shows qmllint's findings for **every `.qml` file of the
open folder**, grouped by file. These are the same problems the source view
underlines, using the project's `.qmlls.ini`.

- Filter by text, or hide errors, warnings or notes.
- Click a finding to open its file in the source view at that line.
- The list fills in while the project is indexed, follows your edits, and
  updates when files change on disk.

Many findings come with a **quick fix**:

- **Fix** on a finding (its tooltip says what it does)
- **Fix *n*** on a file, for the file's safe fixes
- **Fix All** for every safe fix in the project

Fixes become **unsaved changes**. A file that isn't open opens as a background
tab, so you can review a fix, undo it there, and save with *Save All*
(Ctrl+L). Some fixes need you to choose an id; they show *Fix…*, which opens
the spot in the source view (press Alt+Return there).

The tab's title counts the HIG issues of the current document plus the
project's qmllint errors and warnings.

---

## 7. Working with a project

### Creating a project

**New Project…** (welcome screen, the *Files* tab without a folder, or the ☰
menu) creates a project: a folder with a first user interface file.

1. Give the project a **name**. It becomes the folder's name and the
   window's title.
2. Choose the folder to **create it in**. Kreator suggests the one you used
   last (the first time: where your last project is, or your documents).
3. Choose what to **start with**:
   - **Kirigami Application**: `Main.qml`, a window with an empty scrollable
     page. This is the skeleton every Kirigami application starts from.
   - **Qt Quick Application**: `Main.qml`, a window with plain Qt Quick
     Controls.
   - **Qt Widgets Form**: `form.ui`, an empty form with a layout.
4. **Create.** The dialog says which file it creates, or why it can't (the
   folder exists and isn't empty, for example; nothing is ever overwritten).

The folder opens as the project and its file in the design view, with the
*Add* tab shown. Documents you had open stay open.

A QML project needs nothing else to run: press **Run** (see below), or type
`qml6 Main.qml` in a terminal in the project's folder.

Its texts are translated with `qsTr()`, which works there, and Kreator keeps
using `qsTr()` for what you add. (KDE's `i18n()` only exists inside an
application that sets it up; when you give the project a launcher that does,
replace the calls.)

[The walkthrough](#12-walkthrough-a-to-do-app-from-an-empty-project) builds
a small application this way.

### Running the application

There are two ways to try what you build:

- **Interact** in the preview's toolbar: use the application right in the
  design view.
- **Run** in the toolbar (**Ctrl+Shift+R**): start it as an application of its
  own, in its own window, exactly as it will start for its users. Kreator
  uses Qt's `qml6` for this, so it works for applications made of QML files;
  one with a launcher of its own (C++, Python, Rust) is started the way its
  project says.

What *Run* starts:

- the project's `Main.qml` (or `main.qml`), while one of the project's files
  is shown, or none
- else the QML file that is shown. An untitled one is saved first: you are
  asked where.

Before it starts, Kreator saves the unsaved changes to the application's
files (those in the folder of the file that is run), because what runs is
what is on disk. Edits in the source view are applied first.

While the application runs, the button is **Stop**. Closing the
application's window ends it as well, and so does quitting Kreator. To see a
change, stop it and run it again.

**Run Output…** in the ☰ menu shows what the application printed: its
`console.log()` messages, and the warnings and errors of the QML engine,
with file names and line numbers. You don't have to keep it open: the first
error of a run is shown as a notification, as is an application that
couldn't be started or ended with an error, each with *Show Output*.

### Opening a folder

**Open Folder…** (welcome screen or ☰ menu) opens a folder as a project.

- The **Files** tab lists its `.qml` and `.ui` files. Hidden folders and
  build output (`build/`, `target/`, …) are left out, and the list follows
  files being added or removed. Use *Filter files…* to find one.
- **Click a file** to open it. Each document keeps its unsaved changes, undo
  history and selection while you work on another one, so switching never asks
  to save. You are only asked when closing the folder or quitting, and then
  only if Kreator isn't set to keep unsaved changes (see
  [Sessions](#8-sessions-picking-up-where-you-left-off)).
- **Quick Open** (**Ctrl+Alt+O**) searches open documents, then the
  project's files, then recent files. The previous document is listed first,
  so Ctrl+Alt+O, Enter switches back.

### Tabs

- **Ctrl+Tab** / **Ctrl+Shift+Tab** (or Ctrl+PgDown / Ctrl+PgUp) cycle through
  the tabs.
- **Ctrl+W** or a middle-click closes a tab. A tab with unsaved changes shows
  a dot, which turns into a close button when you hover it.
- Drag tabs to reorder them.
- When the tabs don't fit, scroll the bar with the wheel or the arrow buttons.
  The list button shows all documents.

### In the background

When a folder is open, Kreator's qmlls reads every `.qml` file of the project
in the background. That fills the qmllint list and makes symbols and the first
completion quick. Progress shows at the bottom of the sidebar. The file you're
looking at is read first, and files changed by other programs are read again.

Files from different projects (a folder with its own `.qmlls.ini` or git
checkout) get a qmlls each. Up to three stay running, so switching between
tabs of different projects doesn't restart anything.

### Files changed by other programs

If a file you have open is changed on disk, for example saved in another
editor:

- without unsaved changes in Kreator, it is reloaded, keeping your selection.
  The reload can be undone.
- with unsaved changes, a bar asks whether to **Load Their Version** or
  **Keep Mine**.

A file changed while it was in a background tab is handled when you switch to
it. To be asked every time instead of reloading automatically, change *Changes
on disk* in the settings.

---

## 8. Sessions: picking up where you left off

When you start Kreator, it reopens the folder and documents of last time, in
the same order, with the same document current. By default it also keeps:

- **unsaved changes** and **untitled documents**, so quitting doesn't ask to
  save
- **undo history**, so Ctrl+Z still goes back past the restart
- **source edits that were never applied**, even ones that don't parse yet
- the places of objects you moved in the signal flow view

The session is saved every 15 seconds (when something changed) and on quit,
so a crash loses at most that much. It is stored in
`~/.local/share/kreator/session.json`.

A few details:

- Undo history is dropped, rather than misapplied, for a file that was changed
  on disk while Kreator was closed.
- Opening a file from the command line adds it to the restored session.
- Only the first running Kreator uses the session. A second window started
  meanwhile neither restores nor overwrites it, and asks about unsaved changes
  on quit.

Under *Configure Kreator…* → *On start* you can turn off keeping unsaved work
(then Kreator asks to save on quit), or turn session restore off entirely. *Save
session every* sets the interval; *Only on quit* saves only when you quit.

---

## 9. Other editors

Kreator works alongside your text editor.

- **Open in Kate** (**Ctrl+Shift+O**, the button in the source view, or *Show
  in Kate* in the outline's menu) opens the file in Kate at the selected
  object's line and column. Kate is found automatically, also as a Flatpak.
- **Open With** in the ☰ menu lists all configured editors.
- Unsaved changes are saved before the editor starts.
- When you save the file in the other editor, Kreator reloads it (see
  [Files changed by other programs](#files-changed-by-other-programs)).

Any other editor (Zed, VS Code, VSCodium, Sublime Text, Neovim, Emacs, …) can
be added under *Configure Kreator…* → *Other Editors* → **Add Editor…**. Give
the program and an argument template. In the template, `{file}`, `{line}`,
`{column}` and `{dir}` are replaced with the file, the selected object's
position and the file's folder. Templates for common editors are offered.

---

## 10. Settings

**Configure Kreator…** (☰ menu, or **Ctrl+Shift+,**) opens the settings.

| Setting | What it does |
|---|---|
| *Open files with* | The editor *Open in …* and Ctrl+Shift+O use. |
| *Changes on disk* | Reload a changed file automatically when it has no unsaved changes. |
| *On start* | Reopen the last folder and documents, and whether to keep unsaved changes, new documents and undo history. |
| *Save session every* | How often the session is saved (or only on quit). |
| **QML Language Server** | Turn qmlls on or off for the source view, turn semantic highlighting on or off, and choose the qmlls program. Leave the program empty to find it automatically. |
| **Kate** | The Kate session to open files in; *Use Kate's editor* for the source view (needs a restart); for the built-in editor, whether to use Kate's colour theme, font and indentation; whether to always open a new Kate window; whether to go to the selected object. |
| **Other Editors** | Add, change or remove editors (see [Other editors](#9-other-editors)). |

Kate's own editor and LSP client settings are changed with *Configure Editor…*
in the source view, and are shared with Kate.

Where Kreator keeps things:

| File | Contents |
|---|---|
| `~/.config/kreator/kreator.conf` | Kreator's settings, recent files and folders, window state. |
| `~/.local/share/kreator/session.json` | The session: open documents, unsaved changes, undo history. |
| `~/.config/kreatorrc` | Kate's editor and LSP client settings as used in Kreator; Kate's groups are copied from `~/.config/katerc`, and changes are written back there. |

---

## 11. Troubleshooting

**The preview looks different from my running application, or shows an
error.** The preview runs inside Kreator, so your application's C++ types,
context properties and singletons don't exist there.

- Bindings to things the preview can't provide are left out, and a notice
  above the preview lists them.
- Modules that only exist inside your application's executable (cxx-qt's
  `new_qml_module`, a static `qt_add_qml_module`) are simulated:
  - Kreator looks for the module's build `qmldir` near the file (for example
    under `build/` or `target/`).
  - It uses your source `.qml` files, so your current edits show.
  - It gives C++ or Rust types placeholder objects with the same properties,
    signals and methods.
  - A file that is part of such a module doesn't have to import it: the
    module's types, such as a C++ singleton the file uses, are found by the
    build `qmldir` that lists the file. For this the file has to be in a
    project: a folder with a Git repository or a build description
    (`CMakeLists.txt`, `Cargo.toml`, `meson.build`), with the build inside it.
- Build your project once so that Kreator can find this output.
- `i18n()` works through a small stand-in.

**Run says qml6 was not found.** Install Qt's declarative tools (the package
that also has qmlls, for example `qt6-declarative-tools`).

**The application runs in the preview but shows empty texts when run.** It
uses `i18n()`, which only exists inside an application that sets it up (the
preview has a stand-in). *Run Output…* shows "i18n is not defined". Use
`qsTr()`, or run it with its own launcher.

**A Plasma applet isn't previewed.** Applets need a running Plasma shell. You
can still edit them in Kreator; test them with `plasmoidviewer`.

**The source view isn't Kate's editor.** Check the terminal output when
Kreator starts. It says why the editor module couldn't be built, usually a
missing package (`kf6-ktexteditor-devel`, `qt6-declarative-devel`, `cmake`,
`gcc-c++`). Also check that *Use Kate's editor* is on in the settings.

**No completion, diagnostics or qmllint list.** qmlls isn't installed or wasn't
found. Install Qt's declarative tools, or set the program under *Configure
Kreator…* → *QML Language Server*.

**Imports of my application's own modules are reported as missing.** Add a
`.qmlls.ini` to your project (Qt Creator and `qt_add_qml_module` can generate
one), or start Kreator with `-I path/to/qml/modules`.

**A menu or dialog is covered by the source view.** Kate's editor is a native
window drawn above the rest. While a Kreator menu or dialog overlaps it,
Kreator shows a snapshot of the editor in its place. If a popup is still
covered, please report it.

---

## 12. Walkthrough: a to-do app from an empty project

This builds the to-do app of the
[Kirigami Design Guide's tutorial](https://n4n0gh.github.io/Doku/tutorial/overview/)
without leaving Kreator. The tutorial explains what each part is for and why;
this section says how each of its steps is done here. The result is in
`examples/tasks/Main.qml`.

Throughout: select objects in the **Outline** tab (or by clicking them in the
preview), add components from the **Add** tab, and set properties in the
panel on the right, with the fields at its bottom for properties that aren't
listed yet. Functions are typed in the **source view** (Ctrl+Shift+E, then
*Apply* or Ctrl+Return). Try each step with **Interact** in the preview's
toolbar.

**Start:** *New Project…*, name it "Tasks", start with *Kirigami
Application*. You get the window (`root`) with its page, sized and titled as
in the tutorial.

**1. A window and a page.** Add a *Label* (it goes on the page) and change
its `text`.

**2. A list of tasks.**

1. Select the window and add a *ListModel*; set its id to `tasksModel`.
2. Add a *ListElement* to it. Give it the fields with the fields at the
   bottom of the properties panel: `title` = `"Water the plants"`, `done` =
   `true`. *Duplicate* it twice (Ctrl+D) and change the copies.
3. Delete the label. Select the page and add a *ListView*. Set its `model`
   to `tasksModel` (⋮ → *Edit as Expression*) and add `currentIndex` = `-1`.
4. Select the view's delegate in the outline and change its **Type** to
   `QQC2.CheckDelegate`. Declare its data: add `required property string
   title` and `required property bool done` (typed as the property's name).
   Set `text` to `title` and add `checked` = `done`.

**3. Adding tasks.**

1. In the source view, add the function `addTask` to the window.
2. Select the page. Under **Add to**, choose `header`, then click *ToolBar*.
3. The tool bar is selected now: choose `contentItem`, then click
   *ActionTextField*. Set its id to `newTaskField` and its `placeholderText`,
   and add `onAccepted` = `{ root.addTask(text); clear() }`.
4. Select the field's action (under `rightActions` in the outline). Change
   its `text`, and add `enabled` and `onTriggered`.

**4. Ticking off and deleting.**

1. Select the delegate. Change its type to `QQC2.ItemDelegate`, set its id
   to `row`, remove `text` and `checked` (⋮ → *Remove*), and add `onClicked`.
2. Choose `contentItem` under **Add to** and click *RowLayout*. Add a
   *CheckBox*, a *Label* and a *ToolButton* (each lands after the one
   before). For the label, switch on `Layout.fillWidth`, which is offered
   because its parent is a layout, and add `elide`, `font.strikeout` and
   `opacity`. The tool button comes with a tooltip and shows only its icon.
3. In the source view, add the function `deleteTask`.

**5. The empty state and a counter.**

1. Select the list view, set its id to `tasksView` and add a
   *PlaceholderMessage*. Change its texts and add `visible`.
2. Select the window. Add `property int remaining` = `0` and
   `Component.onCompleted` = `recount()`, and a *Connections* object with
   `target` = `tasksModel`. Its `onCountChanged` and `onDataChanged`
   functions, and the function `recount`, are typed in the source view.
3. Select the page, choose `footer` under **Add to** and click *ToolBar*; add
   `visible`. Choose `contentItem` and click *Label*; set its `text` (as an
   expression) and add `leftPadding`.

**6. Filtering.**

1. Select the window. Add `property string filter` = `"all"` and
   `onFilterChanged`, then a *KSortFilterProxyModel*: set its id to
   `visibleTasks`, its `sourceModel` to `tasksModel`, and add
   `filterRowCallback`. Point the list view's `model` at `visibleTasks`.
2. Select the page and add an *Action* (it goes into the page's `actions`):
   "Show". With it selected, add another *Action*: an action inside an action
   is a menu entry. Set it up, then duplicate it twice for the other two
   choices. Select the page again and add the "Clear Completed" action.
3. The handlers that touch the data (`onClicked`, `onToggled`) are changed
   under *Signal handlers* in the properties panel; the functions
   `sourceRow` and `clearCompleted` are added in the source view.

**7. Remembering the list.** Delete the three list elements. Select the
window and add *Settings*: set `location`, and add `property string tasks` =
`"[]"`. The functions `load` and `save`, and their calls, go into the source
view.

Then press **Run** (Ctrl+Shift+R): the changes are saved and the application
starts in its own window. Add some tasks, close it, run it again: they are
still there.

---

## Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Open / Save / Save As | Ctrl+O / Ctrl+S / Ctrl+Shift+S |
| Save All | Ctrl+L |
| Reload / Close | F5 / Ctrl+W |
| Quit | Ctrl+Q |
| Undo / Redo | Ctrl+Z / Ctrl+Shift+Z |
| Design ↔ source view | Ctrl+Shift+E |
| Signal flow view | Ctrl+Shift+G |
| Run / stop the application | Ctrl+Shift+R |
| Apply source edits | Ctrl+Return |
| Quick Open / Go to Symbol | Ctrl+Alt+O / Ctrl+Alt+P |
| Next / previous tab | Ctrl+Tab / Ctrl+Shift+Tab (or Ctrl+PgDown / Ctrl+PgUp) |
| Show or hide the sidebar | F9 |
| Open in Kate (or your default editor) | Ctrl+Shift+O |
| Configure Kreator | Ctrl+Shift+, |
| Delete / Duplicate the selected object | Del / Ctrl+D |
| Cut / Copy / Paste an object | Ctrl+X / Ctrl+C / Ctrl+V |
| Move an object up / down | Alt+Up / Alt+Down |
| Move the selected object to the next grid line / by a pixel (design view focused) | Arrow keys / Shift+arrow keys |
| Resize the selected object to the next grid line / by a pixel (design view focused) | Ctrl+arrow keys / Ctrl+Shift+arrow keys |
| Select the object under the selected one (design view) | Alt+click |
| Place or resize freely while dragging (no snapping) | hold Shift |
| Cancel moving or resizing an object | Escape |
| Zoom the preview | Ctrl+wheel |

In the source view, the editor's own shortcuts apply as well: Kate's (its
actions and their shortcuts are listed in the editor's context menu) or the
built-in editor's (listed in the [README](../README.md#keyboard-shortcuts)).
