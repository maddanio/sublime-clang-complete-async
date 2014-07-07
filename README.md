sublime-clang-complete-async
============================

wrapper around server-part of emacs-clang-complete-async for sublimetext3

Installation:

- copy ClangConpletion into packages folder
- add a section like this to your project file:
```
    "clang_completion":
    {
        "enabled": true,
        "args": ["-I/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/c++/v1/",
                 "-std=c++11",
                 "-I${project_path}"]
    }
```
