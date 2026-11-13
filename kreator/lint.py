"""Checks a document against (a practical subset of) the KDE Human Interface
Guidelines and Kirigami best practices.

Each issue is a dict: uid, severity ("warning" | "hint"), title, detail,
property (optional) and fix (optional fix id understood by apply_fix()).
"""

from __future__ import annotations

import re

from . import qmldoc
from .qmldoc import ObjectNode

USER_VISIBLE = {
    "text", "title", "subtitle", "placeholderText", "explanation", "label", "tooltip",
    "ToolTip.text", "QQC2.ToolTip.text", "Kirigami.FormData.label", "banner.title", "description",
}
SPACING_PROPS = {
    "spacing", "rowSpacing", "columnSpacing", "padding", "leftPadding", "rightPadding",
    "topPadding", "bottomPadding", "horizontalPadding", "verticalPadding",
    "anchors.margins", "anchors.leftMargin", "anchors.rightMargin", "anchors.topMargin",
    "anchors.bottomMargin", "Layout.margins", "Layout.leftMargin", "Layout.rightMargin",
    "Layout.topMargin", "Layout.bottomMargin",
}
SIZE_PROPS = {
    "width", "height", "implicitWidth", "implicitHeight", "Layout.preferredWidth",
    "Layout.preferredHeight", "Layout.minimumWidth", "Layout.minimumHeight",
    "Layout.maximumWidth", "Layout.maximumHeight",
}
COLOR_PROPS = {"color", "border.color", "Kirigami.Theme.backgroundColor", "Kirigami.Theme.textColor"}
BUTTON_TYPES = {"Button", "ToolButton", "Action", "RoundButton", "DelayButton", "MenuItem", "TabButton"}
SENTENCE_TYPES = {"CheckBox", "Switch", "RadioButton", "Label", "InlineMessage"}
_SMALL_WORDS = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "from", "by", "of",
                "in", "with", "as", "into", "via", "per", "vs", "is"}


def _issue(node, title, detail, severity="warning", prop="", fix=""):
    return {"uid": node.uid, "severity": severity, "title": title, "detail": detail,
            "property": prop, "fix": fix}


def is_title_case(text: str) -> bool:
    words = [w for w in re.split(r"[\s/]+", text.replace("&", "")) if w]
    for i, w in enumerate(words):
        core = w.strip("…:.!?()\"'")
        if not core or not core[0].isalpha():
            continue
        if i not in (0, len(words) - 1) and core.lower() in _SMALL_WORDS:
            continue
        if core[0].islower():
            return False
    return True


def to_title_case(text: str) -> str:
    words = text.split(" ")
    out = []
    for i, w in enumerate(words):
        if i not in (0, len(words) - 1) and w.lower() in _SMALL_WORDS:
            out.append(w.lower())
        elif w and w[0].isalpha():
            out.append(w[0].upper() + w[1:])
        else:
            out.append(w)
    return " ".join(out)


# --------------------------------------------------------------------------- QML

def lint_qml(doc: qmldoc.QmlDocument) -> list[dict]:
    issues: list[dict] = []
    if doc.root is None:
        return issues
    kirigami = doc.import_alias("org.kde.kirigami")
    kprefix = (kirigami + ".") if kirigami else "Kirigami."
    uses_kirigami = kirigami is not None

    root = doc.root
    if root.short_type == "ApplicationWindow" and not root.type_name.startswith(kprefix) and uses_kirigami:
        issues.append(_issue(root, "Use Kirigami.ApplicationWindow",
                             "Kirigami.ApplicationWindow provides the page stack, global drawer and "
                             "convergent behaviour expected from KDE applications.", fix="kirigami-window"))

    for node, _depth, parent, _label in doc.walk():
        t = node.short_type
        if t == "Text" and "." not in node.type_name:
            issues.append(_issue(node, "Use Label instead of Text",
                                 "QQC2.Label follows the colour scheme and font settings of the platform.",
                                 fix="text-to-label"))
        for name, b in node.bindings():
            if not isinstance(b.value, str):
                continue
            kind, val = qmldoc.classify(b.value)
            short = name.rsplit(".", 1)[-1] if name.endswith(("FormData.label", "ToolTip.text")) else name
            # (a ListElement holds data, and can't hold script such as i18n())
            if (name in USER_VISIBLE or short in ("label", "text")) and kind == "string" and val.strip() \
                    and t != "ListElement":
                issues.append(_issue(node, f"Untranslated text in “{name}”",
                                     "User-visible strings should be wrapped in i18n() (KDE) or qsTr() so "
                                     "they can be translated.", prop=name, fix="translate"))
            if kind in ("string", "translated") and val.strip():
                if t in BUTTON_TYPES and name == "text" and not is_title_case(val):
                    issues.append(_issue(node, "Button and action text should use Title Case",
                                         f"“{val}” → “{to_title_case(val)}”", severity="hint",
                                         prop=name, fix="title-case"))
                if name.endswith("FormData.label") and not val.rstrip().endswith(":"):
                    issues.append(_issue(node, "Form labels should end with a colon",
                                         f"“{val}” → “{val.rstrip()}:”", severity="hint", prop=name,
                                         fix="add-colon"))
                if t in ("CheckBox", "Switch", "RadioButton") and name == "text" and val.rstrip().endswith(":"):
                    issues.append(_issue(node, "Check box text should not end with a colon",
                                         "Options use sentence case without trailing punctuation.",
                                         severity="hint", prop=name))
                if "..." in val:
                    issues.append(_issue(node, "Use an ellipsis character",
                                         "Write “…” instead of three dots.", severity="hint",
                                         prop=name, fix="ellipsis"))
            if name in SPACING_PROPS and kind == "number" and float(val) not in (0,):
                issues.append(_issue(node, f"Hard-coded spacing in “{name}”",
                                     f"Use {kprefix}Units.smallSpacing / largeSpacing so spacing scales "
                                     "with the user's settings.", prop=name, fix="units-spacing"))
            if name in SIZE_PROPS and kind == "number" and float(val) > 1:
                issues.append(_issue(node, f"Hard-coded size in “{name}”",
                                     f"Express sizes in {kprefix}Units.gridUnit so they follow the font size.",
                                     severity="hint", prop=name, fix="units-size"))
            is_color_prop = name in COLOR_PROPS or name.endswith(("color", "Color"))
            named_color = kind == "string" and re.fullmatch(r"[a-z]+", val or "") and val != "transparent"
            if is_color_prop and (kind == "color" or named_color):
                issues.append(_issue(node, f"Hard-coded colour in “{name}”",
                                     f"Use {kprefix}Theme colours (e.g. textColor, backgroundColor, "
                                     "highlightColor) so the UI follows the colour scheme and dark mode.",
                                     prop=name))
            if name in ("font.pixelSize", "font.pointSize") and kind == "number":
                issues.append(_issue(node, "Hard-coded font size",
                                     f"Use {kprefix}Heading for titles or derive from "
                                     f"{kprefix}Theme.defaultFont so text respects the user's font settings.",
                                     prop=name))
        # icon-only buttons need text for accessibility
        if t in ("ToolButton", "Button", "RoundButton"):
            names = {n for n, _ in node.bindings()}
            if ("icon.name" in names or "icon.source" in names) and "text" not in names:
                issues.append(_issue(node, "Icon-only button without text",
                                     "Set text and use display: AbstractButton.IconOnly with a tooltip, "
                                     "so screen readers can announce the button.", prop="icon.name"))
        if t in ("Page", "ScrollablePage") and node.binding("title") is None and parent is not None:
            issues.append(_issue(node, "Page without a title",
                                 "Pages should have a title; it is shown in the toolbar and window title.",
                                 severity="hint", fix="page-title"))
    return issues


def apply_qml_fix(doc: qmldoc.QmlDocument, issue: dict, tr_fn: str) -> bool:
    node = doc.find(issue["uid"])
    if node is None:
        return False
    fix = issue["fix"]
    prop = issue.get("property")
    kprefix = doc.ensure_import("org.kde.kirigami", "Kirigami") if fix.startswith("units") or fix == "kirigami-window" else ""
    b = node.binding(prop) if prop else None
    if fix == "translate" and b is not None:
        kind, val = qmldoc.classify(b.value)
        b.value = f"{tr_fn}({qmldoc.quote(val)})"
        return True
    if fix in ("title-case", "add-colon", "ellipsis") and b is not None:
        kind, val = qmldoc.classify(b.value)
        new = {"title-case": to_title_case, "add-colon": lambda v: v.rstrip() + ":",
               "ellipsis": lambda v: v.replace("...", "…")}[fix](val)
        b.value = qmldoc.replace_translated_text(b.value, new) if kind == "translated" else qmldoc.quote(new)
        return True
    if fix == "units-spacing" and b is not None:
        v = float(b.value)
        b.value = f"{kprefix}Units.smallSpacing" if v <= 6 else (
            f"{kprefix}Units.largeSpacing" if v <= 12 else f"{kprefix}Units.gridUnit")
        return True
    if fix == "units-size" and b is not None:
        units = round(float(b.value) / 18 * 2) / 2 or 1
        b.value = f"{kprefix}Units.gridUnit * {units:g}" if units != 1 else f"{kprefix}Units.gridUnit"
        return True
    if fix == "text-to-label":
        cprefix = doc.ensure_import("QtQuick.Controls", "QQC2")
        node.type_name = f"{cprefix}Label"
        return True
    if fix == "kirigami-window":
        node.type_name = f"{kprefix}ApplicationWindow"
        return True
    if fix == "page-title":
        node.set_binding("title", f'{tr_fn}("{node.short_type}")')
        return True
    return False


# --------------------------------------------------------------------------- .ui

def lint_ui(doc) -> list[dict]:
    from .uidoc import UiDocument  # noqa: F401  (type only)

    issues: list[dict] = []
    for node, _depth, parent, _label in doc.walk():
        el = node.el
        cls = node.type_name
        props = {p.get("name"): p for p in el.findall("property")}
        if "styleSheet" in props:
            issues.append(_issue(node, "Style sheet overrides the theme",
                                 "Style sheets break Breeze, colour schemes and dark mode. Use palette "
                                 "roles or KColorScheme instead.", prop="styleSheet", fix="remove-prop"))
        for size_prop in ("minimumSize", "maximumSize", "fixedSize"):
            if size_prop in props and cls not in ("QMainWindow", "QDialog", "QWidget") and parent is not None:
                issues.append(_issue(node, f"Fixed {size_prop}",
                                     "Fixed pixel sizes do not adapt to fonts, translations and scaling; "
                                     "rely on layouts and size policies.", severity="hint", prop=size_prop))
        if "font" in props and props["font"].find("font/pointsize") is not None:
            issues.append(_issue(node, "Hard-coded font size",
                                 "Respect the user's font settings; use relative sizes or KFontUtils.",
                                 prop="font"))
        text_el = el.find("property[@name='text']/string")
        if text_el is None:
            text_el = el.find("property[@name='title']/string")
        text = text_el.text if text_el is not None and text_el.text else ""
        if text:
            plain = text.replace("&", "")
            if cls in ("QPushButton", "QToolButton", "QCommandLinkButton") and not is_title_case(plain):
                issues.append(_issue(node, "Button text should use Title Case",
                                     f"“{plain}” → “{to_title_case(plain)}”", severity="hint",
                                     prop="text", fix="title-case"))
            if cls in ("QCheckBox", "QRadioButton") and plain.rstrip().endswith(":"):
                issues.append(_issue(node, "Check box text should not end with a colon",
                                     "Options use sentence case without trailing punctuation.", severity="hint",
                                     prop="text"))
            if "..." in text:
                issues.append(_issue(node, "Use an ellipsis character", "Write “…” instead of three dots.",
                                     severity="hint", prop="text", fix="ellipsis"))
        # labels in form layouts: colon + buddy
        if cls == "QLabel" and parent is not None:
            pel = parent.el
            if pel.tag == "layout" and pel.get("class") == "QFormLayout" and text:
                if not text.rstrip().endswith(":"):
                    issues.append(_issue(node, "Form labels should end with a colon",
                                         f"“{text}” → “{text.rstrip()}:”", severity="hint", prop="text",
                                         fix="add-colon"))
                if "buddy" not in props:
                    issues.append(_issue(node, "Label without buddy",
                                         "Set the buddy property so the label's mnemonic focuses its field "
                                         "and screen readers associate them.", severity="hint", prop="buddy"))
        if node.kind == "layout":
            for p in ("spacing", "margin", "leftMargin", "rightMargin", "topMargin", "bottomMargin",
                      "horizontalSpacing", "verticalSpacing"):
                if p in props:
                    issues.append(_issue(node, f"Hard-coded layout {p}",
                                         "Let the style decide spacing so it matches the rest of the desktop.",
                                         severity="hint", prop=p, fix="remove-prop"))
    return issues


def apply_ui_fix(doc, issue: dict) -> bool:
    node = doc.find(issue["uid"])
    if node is None:
        return False
    fix, prop = issue["fix"], issue.get("property")
    if fix == "remove-prop":
        return doc.remove_property(node, prop)
    s = node.el.find(f"property[@name='{prop}']/string")
    if s is None or s.text is None:
        return False
    if fix == "title-case":
        s.text = to_title_case(s.text)
    elif fix == "add-colon":
        s.text = s.text.rstrip() + ":"
    elif fix == "ellipsis":
        s.text = s.text.replace("...", "…")
    else:
        return False
    return True
