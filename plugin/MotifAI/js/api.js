// .pragma library is deliberately omitted: these helpers close over nothing and
// are imported per-component, which keeps the request state isolated.

// Perform a JSON request against the local Motif service.
function request(base, token, method, path, body, onDone) {
    var xhr = new XMLHttpRequest();
    var url = base.replace(/\/+$/, "") + path;
    try {
        xhr.open(method, url, true);
    } catch (e) {
        onDone({ ok: false, error: "bad server address: " + url, offline: true });
        return null;
    }
    xhr.setRequestHeader("Content-Type", "application/json");
    if (token && token.length > 0)
        xhr.setRequestHeader("X-Motif-Token", token);

    xhr.onreadystatechange = function () {
        if (xhr.readyState !== XMLHttpRequest.DONE)
            return;
        if (xhr.status === 0) {
            onDone({ ok: false, offline: true,
                     error: "Could not reach the Motif engine at " + base });
            return;
        }
        var parsed = null;
        try {
            parsed = JSON.parse(xhr.responseText);
        } catch (e) {
            onDone({ ok: false, error: "The engine returned a malformed reply.",
                     status: xhr.status });
            return;
        }
        if (xhr.status === 401) {
            onDone({ ok: false, unauthorised: true,
                     error: "The panel and the Motif engine don't recognise each other. " +
                            "Open Motif Setup and choose Repair." });
            return;
        }
        if (xhr.status >= 400 && parsed && parsed.error) {
            onDone({ ok: false, error: parsed.error, status: xhr.status });
            return;
        }
        onDone(parsed);
    };

    try {
        xhr.send(body ? JSON.stringify(body) : "");
    } catch (e) {
        onDone({ ok: false, offline: true, error: "Request failed: " + e });
    }
    return xhr;
}

function health(base, token, onDone) {
    return request(base, token, "GET", "/health", null, onDone);
}

function compose(base, token, payload, onDone) {
    return request(base, token, "POST", "/compose", payload, onDone);
}

// Composing takes minutes, so the panel starts a job and watches it.
function startJob(base, token, payload, onDone) {
    return request(base, token, "POST", "/jobs", payload, onDone);
}

function job(base, token, id, onDone) {
    return request(base, token, "GET", "/jobs/" + id, null, onDone);
}

function cancelJob(base, token, id, onDone) {
    return request(base, token, "POST", "/jobs/" + id + "/cancel", {}, onDone);
}

// The composer's settings, such as how much care it takes.
function settings(base, token, onDone) {
    return request(base, token, "GET", "/settings", null, onDone);
}

function saveSettings(base, token, values, onDone) {
    return request(base, token, "POST", "/settings", values, onDone);
}

// Polled while a composition is in flight, so the panel can show what Motif
// is actually doing rather than a generic spinner.
function progress(base, token, onDone) {
    return request(base, token, "GET", "/progress", null, onDone);
}

function plan(base, token, payload, onDone) {
    return request(base, token, "POST", "/plan", payload, onDone);
}

// Preferences has no lists to populate — composer and instrumentation are
// never chosen from a menu, only asked for in the prompt.
function savePrefs(base, token, prefs, onDone) {
    return request(base, token, "POST", "/preferences", prefs, onDone);
}

function prefsFromConfig(rawText) {
    if (!rawText || rawText.length === 0)
        return null;
    try {
        var cfg = JSON.parse(rawText);
        return cfg.preferences || null;
    } catch (e) {
        return null;
    }
}

// Pull the shared token out of ~/.motif/config.json without a JSON parse
// failure taking the panel down.
function tokenFromConfig(rawText) {
    if (!rawText || rawText.length === 0)
        return "";
    try {
        var cfg = JSON.parse(rawText);
        return cfg.token || "";
    } catch (e) {
        var m = /"token"\s*:\s*"([^"]+)"/.exec(rawText);
        return m ? m[1] : "";
    }
}

function portFromConfig(rawText, fallback) {
    if (!rawText || rawText.length === 0)
        return fallback;
    try {
        var cfg = JSON.parse(rawText);
        return cfg.port || fallback;
    } catch (e) {
        var m = /"port"\s*:\s*(\d+)/.exec(rawText);
        return m ? parseInt(m[1], 10) : fallback;
    }
}
