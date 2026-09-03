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
                     error: "The plugin's token does not match the engine's. " +
                            "Open Settings and paste the token from ~/.motif/config.json." });
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

function plan(base, token, payload, onDone) {
    return request(base, token, "POST", "/plan", payload, onDone);
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
