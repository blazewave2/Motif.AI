// Turning what Motif says into something the conversation can show.
//
// Replies arrive as plain text with a little Markdown (**bold**, *italic*),
// but the conversation is drawn as Qt's StyledText, where "<" and "&" are
// markup: a note mentioning "bars 12 < 16" would otherwise vanish mid-line.
// Plain ES5 throughout, for the Qt 5.9 inside MuseScore 3 — and no function
// named after a JavaScript built-in: Qt 5.9 resolves a call to escape() to
// the global one, which URL-encodes, even from inside this file.
.pragma library

// Where each MuseScore keeps a plugin's keyboard shortcut.
function shortcutHint(major) {
    var where = major >= 4
        ? "open Plugins → Manage plugins, click Motif.AI, and choose Edit shortcut."
        : "open Plugins → Plugin Manager, select Motif.AI, and choose Define Shortcut.";
    return "MuseScore doesn't let a plugin add its own toolbar button, but you can give "
         + "Motif a one-key shortcut instead: " + where;
}

function escapeMarkup(s) {
    return String(s === undefined || s === null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function rich(s) {
    var t = escapeMarkup(s);
    t = t.replace(/\*\*([^*\n]+?)\*\*/g, "<b>$1</b>");
    t = t.replace(/(^|[\s(“"])\*([^*\s](?:[^*\n]*[^*\s])?)\*(?=$|[\s).,;:!?”"])/g,
                  "$1<i>$2</i>");
    t = t.replace(/(^|[\s(“"])_([^_\s](?:[^_\n]*[^_\s])?)_(?=$|[\s).,;:!?”"])/g,
                  "$1<i>$2</i>");
    return t.replace(/\r?\n/g, "<br>");
}
