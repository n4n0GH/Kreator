"""A previewed document doesn't see Kreator's own objects (`Backend`, `Lsp`,
`TextLayout`): an application's own `Backend` is not Kreator's."""

backend.openFile(OUT + "/work/UsesBackend.qml")


def shown():
    o = backend.previewObject
    check(backend.previewError == "", f"the preview is made ({backend.previewError!r})")
    for name in ("seesBackend", "seesLsp", "seesTextLayout"):
        check(o.property(name) is False, f"{name[4:]} is not defined in the preview")
    QTimer.singleShot(300, noted)


def noted():
    check("Backend is not defined" in backend.previewNote, f"using it is reported ({backend.previewNote!r})")
    check(page is not None and backend.fileName == "UsesBackend.qml", "Kreator's own interface still has its Backend")
    app.quit()


wait_until(lambda: backend.previewObject is not None and backend.fileName == "UsesBackend.qml", shown,
           what="the preview is shown")
