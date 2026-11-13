cmake_minimum_required(VERSION 3.22)
project(kreator_kate LANGUAGES CXX)

# A QML module that puts Kate's editor (the KTextEditor framework) into
# Kreator's QML UI. It links the system's libKF6TextEditor dynamically, so
# updates of KTextEditor / Kate from the distribution apply without a rebuild
# (Kate's LSP client plugin is loaded from Kate's installation at run time)
# (KF6 stays binary compatible within 6.x).

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.6 REQUIRED COMPONENTS Core Gui Widgets Qml Quick)
find_package(KF6TextEditor REQUIRED)
find_package(KF6Config REQUIRED)
find_package(KF6XmlGui REQUIRED)
find_package(KF6CoreAddons REQUIRED)
find_package(KF6WidgetsAddons REQUIRED)
find_package(KF6I18n REQUIRED)

qt_standard_project_setup(REQUIRES 6.6)

# the module ends up in <build>/qml/org/kde/kreator/kate
set(QT_QML_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/qml)

qt_add_qml_module(kreator_kate
    URI org.kde.kreator.kate
    VERSION 1.0
    PLUGIN_TARGET kreator_kate
    SOURCES
        nativeitem.h nativeitem.cpp
        kateeditor.h kateeditor.cpp
        katetoolarea.h katetoolarea.cpp
        katehost.h katehost.cpp
        sharedsettings.h sharedsettings.cpp
)

target_link_libraries(kreator_kate PRIVATE
    Qt6::Core Qt6::Gui Qt6::Widgets Qt6::Qml Qt6::Quick
    KF6::TextEditor
    KF6::ConfigCore
    KF6::XmlGui
    KF6::CoreAddons
    KF6::WidgetsAddons
    KF6::I18n
)

# Kate's plugins (its LSP client) are loaded at run time from the system: they
# need Kate installed, but nothing of Kate is needed to build this
