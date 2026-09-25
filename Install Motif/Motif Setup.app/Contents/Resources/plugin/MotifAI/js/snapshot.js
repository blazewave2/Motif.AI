.pragma library

// The open score, read with MuseScore's cursor.
//
// MuseScore 4's plugins cannot save a score (its writeScore is not
// implemented), so where MuseScore 3 hands Motif the page as MusicXML the
// panel walks it instead, and the engine rebuilds the score from what it
// finds: every chord and rest with its exact timing and spelled pitches, the
// bars with their time and key signatures, and the tempo and dynamic marks.
//
// `E` carries the element type numbers, which differ between MuseScore 3 and 4
// and can only be read where the MuseScore module is imported.

var FORMAT = "motif-snapshot-1";
var MAX_EVENTS = 80000;          // a very large score is cut off, not sent whole

function _str(v) {
    return (v === undefined || v === null) ? "" : String(v);
}

function _ticks(f) {
    try { return f ? f.ticks : 0; } catch (e) { return 0; }
}

function walk(score, E) {
    var out = { format: FORMAT, title: "", composer: "", parts: [], measures: [],
                events: [], tempos: [], dynamics: [], truncated: false };
    try { out.title = _str(score.title); } catch (e) {}
    try { if (!out.title) out.title = _str(score.metaTag("workTitle")); } catch (e) {}
    try { out.composer = _str(score.metaTag("composer")); } catch (e) {}

    for (var p = 0; p < score.parts.length; ++p) {
        var part = score.parts[p];
        var rec = { name: "", short: "", instrument: "", program: -1,
                    startTrack: part.startTrack, endTrack: part.endTrack };
        try { rec.name = _str(part.longName || part.partName); } catch (e) {}
        try { rec.short = _str(part.shortName); } catch (e) {}
        try { rec.instrument = _str(part.instrumentId); } catch (e) {}
        try { rec.program = part.midiProgram; } catch (e) {}
        out.parts.push(rec);
    }

    // bars: where each starts, how long it really is (a pickup is short) and
    // the time signature it is written in
    var m = score.firstMeasure;
    while (m) {
        var bar = { tick: m.firstSegment.tick, len: 0, ts: [4, 4] };
        try { bar.len = m.timesigActual.ticks; } catch (e) {}
        try { bar.ts = [m.timesigNominal.numerator, m.timesigNominal.denominator]; } catch (e) {}
        out.measures.push(bar);
        m = m.nextMeasure;
    }

    var cursor = score.newCursor();
    // the key signature of each bar, as the first staff has it
    cursor.track = 0;
    cursor.rewind(0);
    out.keys = [];
    var guard = 0;
    while (cursor.segment && guard++ < 100000) {
        out.keys.push([cursor.tick, cursor.keySignature]);
        if (!cursor.nextMeasure())
            break;
    }

    for (var track = 0; track < score.ntracks; ++track) {
        cursor.track = track;
        cursor.rewind(0);
        while (cursor.segment) {
            var el = cursor.element;
            if (el && (el.type === E.CHORD || el.type === E.REST)) {
                if (out.events.length >= MAX_EVENTS) {
                    out.truncated = true;
                    break;
                }
                var notes = 0;
                if (el.type === E.CHORD) {
                    notes = [];
                    for (var k = 0; k < el.notes.length; ++k) {
                        var n = el.notes[k];
                        notes.push([n.pitch, n.tpc, n.tieForward ? 1 : 0, n.tieBack ? 1 : 0]);
                    }
                }
                var ev = [track, cursor.tick, _ticks(el.actualDuration) || _ticks(el.duration),
                          0, 0, notes, 0, 0, 0];
                try { ev[3] = el.duration.numerator; ev[4] = el.duration.denominator; } catch (e) {}
                try {
                    if (el.tuplet) {
                        ev[6] = el.tuplet.actualNotes;
                        ev[7] = el.tuplet.normalNotes;
                        ev[8] = _ticks(el.tuplet.actualDuration) || _ticks(el.tuplet.globalDuration);
                    }
                } catch (e) {}
                out.events.push(ev);
            }
            var anns = cursor.segment.annotations;
            for (var a = 0; anns && a < anns.length; ++a) {
                var an = anns[a];
                if (an.track !== track)
                    continue;
                if (an.type === E.TEMPO_TEXT) {
                    var qps = 0;
                    try { qps = an.tempo; } catch (e) {}
                    out.tempos.push([cursor.tick, qps * 60, _str(an.text)]);
                } else if (an.type === E.DYNAMIC) {
                    out.dynamics.push([cursor.tick, track, _str(an.text)]);
                }
            }
            cursor.next();
        }
        if (out.truncated)
            break;
    }
    return out;
}
