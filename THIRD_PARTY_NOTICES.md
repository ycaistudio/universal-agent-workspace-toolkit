# Third-party notices

## grok-bot-backup

The Grok Bot profile in this toolkit follows the on-box layout described by
[company-notes/grok-bot-backup](https://github.com/company-notes/grok-bot-backup)
(agent directories, user `workflows/` versus `managed-skills/` and
`plugin-skills/`, the memory-drop JSONL tree, and a read-only SQLite snapshot
of `search-index.db`). That project is export-only. The scan, pack, restore,
and checklist in this repository are separate code.

`toolkit_grok.py` does not vendor that project's modules. The layout and the
idea of copying `search-index.db` with SQLite's backup API were studied from
it. Its license is reproduced below.

```text
MIT License

Copyright (c) 2026 company-notes

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
