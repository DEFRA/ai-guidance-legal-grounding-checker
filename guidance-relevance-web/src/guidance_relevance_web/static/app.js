(function () {
  function $(id) { return document.getElementById(id); }

  function checkedValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((el) => el.value);
  }

  function setCheckedValues(name, values) {
    const raw = Array.isArray(values) ? values : String(values || "").split(",");
    const wanted = new Set(raw.map((v) => String(v).trim().toLowerCase()).filter(Boolean));
    document.querySelectorAll(`input[name="${name}"]`).forEach((el) => {
      const slug = el.value;
      el.checked = wanted.has(slug) || wanted.has(slug.replace(/_/g, "-"));
    });
    const list = document.getElementById(name + "-list");
    if (list) list.dispatchEvent(new Event("change"));
  }

  function initFilterableCheckboxes(opts) {
    const filter = $(opts.filterId);
    const list = $(opts.listId);
    const meta = $(opts.metaId);
    const selected = $(opts.selectedId);
    if (!filter || !list) return;
    const items = () => Array.from(list.querySelectorAll(".govuk-checkboxes__item"));
    const heading = selected && selected.querySelector(".scope-selected__heading");
    const chips = selected && selected.querySelector(".scope-selected__list");
    const clearBtn = selected && selected.querySelector(".scope-selected__clear");

    function renderSelected() {
      if (!selected || !chips) return;
      const checked = Array.from(list.querySelectorAll("input[type=checkbox]:checked"));
      selected.hidden = checked.length === 0;
      if (heading) heading.textContent = `Selected ${opts.noun} (${checked.length})`;
      chips.replaceChildren();
      checked.forEach((input) => {
        const label = list.querySelector(`label[for="${CSS.escape(input.id)}"]`);
        const name = label ? label.textContent.trim() : input.value;
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "scope-selected__chip";
        btn.setAttribute("aria-label", `Remove ${name}`);
        const x = document.createElement("span");
        x.className = "scope-selected__remove";
        x.setAttribute("aria-hidden", "true");
        x.textContent = "×";
        const text = document.createElement("span");
        text.className = "scope-selected__name";
        text.textContent = name;
        btn.append(x, text);
        btn.addEventListener("click", () => {
          input.checked = false;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        });
        li.append(btn);
        chips.append(li);
      });
    }

    function update() {
      const q = filter.value.trim().toLowerCase();
      let shown = 0;
      items().forEach((item) => {
        const hay = (item.getAttribute("data-search") || item.textContent || "").toLowerCase();
        const visible = !q || hay.includes(q);
        item.hidden = !visible;
        if (visible) shown += 1;
      });
      renderSelected();
      if (!meta) return;
      const n = checkedValues(opts.name).length;
      const total = items().length;
      if (n) {
        meta.textContent = `${n} selected · ${shown} shown`;
      } else if (q) {
        meta.textContent = shown ? `${shown} shown` : "No organisations match";
      } else {
        meta.textContent = `${total} ${opts.noun}`;
      }
    }
    filter.addEventListener("input", update);
    filter.addEventListener("search", update);
    filter.addEventListener("keydown", (e) => {
      if (e.key === "Enter") e.preventDefault();
    });
    list.addEventListener("change", update);
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        items().forEach((item) => {
          const input = item.querySelector("input[type=checkbox]");
          if (input) input.checked = false;
        });
        list.dispatchEvent(new Event("change"));
      });
    }
    update();
    return update;
  }

  function optionParts(opt) {
    if (Array.isArray(opt)) {
      return { value: opt[0], label: opt[1], aliases: opt[2] || [] };
    }
    return { value: opt.value, label: opt.label, aliases: opt.aliases || [] };
  }

  function renderScopeCheckboxes(listId, name, options) {
    const list = $(listId);
    if (!list) return;
    const kept = new Set(checkedValues(name));
    list.replaceChildren();
    (options || []).forEach((opt) => {
      const { value, label, aliases } = optionParts(opt);
      const item = document.createElement("div");
      item.className = "govuk-checkboxes__item";
      item.setAttribute("data-search", [value, label].concat(aliases).join(" "));
      const id = `${name}-${value}`;
      const input = document.createElement("input");
      input.className = "govuk-checkboxes__input";
      input.id = id;
      input.name = name;
      input.type = "checkbox";
      input.value = value;
      input.checked = kept.has(value) || kept.has(String(value).replace(/_/g, "-"));
      const lab = document.createElement("label");
      lab.className = "govuk-label govuk-checkboxes__label";
      lab.htmlFor = id;
      lab.textContent = label;
      item.append(input, lab);
      list.append(item);
    });
    list.dispatchEvent(new Event("change"));
  }

  function snapshots() {
    if (window.GRF_SNAPSHOTS) return window.GRF_SNAPSHOTS;
    const el = $("snapshots-data");
    if (!el) return [];
    try { return JSON.parse(el.textContent); } catch (_e) { return []; }
  }

  function snapshotById(id) {
    const all = snapshots();
    return all.find((s) => s.id === id) || all[0] || null;
  }

  function applySnapshotScope(id) {
    const snap = snapshotById(id);
    if (!snap) return;
    renderScopeCheckboxes("organisations-list", "organisations", snap.organisation_options);
    renderScopeCheckboxes("document_types-list", "document_types", snap.document_type_options);
  }

  function fields() {
    return {
      email: $("email") && $("email").value,
      name: $("name").value,
      description: $("description").value,
      exclusion_criteria: $("exclusion_criteria").value,
      keep_hints: $("keep_hints").value,
      drop_hints: $("drop_hints").value,
      lexicon: $("lexicon").value,
      organisations: checkedValues("organisations"),
      document_types: checkedValues("document_types"),
      corpus_id: $("corpus_id") && $("corpus_id").value,
    };
  }

  const PALETTE = {
    preview_in: "#1d70b8",
    corpus_in: "#1d70b8",
    organisation_pass: "#1d70b8",
    document_type_pass: "#4c2c92",
    lexicon_hit: "#1d70b8",
    would_route: "#00703c",
    organisation_miss: "#505a5f",
    document_type_miss: "#6f777b",
    missing_body: "#505a5f",
    empty_body: "#6f777b",
    lexicon_miss: "#b1b4b6",
    cosine_miss: "#b1b4b6",
    pass1_false: "#d4351c",
    pass1_true: "#4c2c92",
    pass2_drop: "#f47738",
    pass2_keep: "#00703c",
    pass2_unadjudicated: "#85994b",
  };

  function fmt(n) {
    return Number(n || 0).toLocaleString("en-GB");
  }

  function showCostEstimate(el, est) {
    if (!el) return;
    if (!est || !(est.html || est.summary)) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.innerHTML = est.html || est.summary;
  }

  function selectedLlmMode() {
    const checked = document.querySelector('input[name="llm_mode"]:checked');
    return checked && checked.value === "sync" ? "sync" : "batch";
  }

  let costEstimates = { batch: null, sync: null };

  function showSelectedCostEstimate() {
    const mode = selectedLlmMode();
    showCostEstimate($("preview-cost"), costEstimates[mode]);
  }

  document.querySelectorAll('input[name="llm_mode"]').forEach((el) => {
    el.addEventListener("change", showSelectedCostEstimate);
  });

  function statusLabel(status) {
    return ({
      queued: "Queued",
      running: "Running",
      done: "Done",
      failed: "Failed",
      blocked_cap: "Over cap",
    }[status] || status || "—");
  }

  function tagClass(status) {
    return "govuk-tag " + ({
      done: "govuk-tag--green",
      failed: "govuk-tag--red",
      running: "govuk-tag--blue",
      blocked_cap: "govuk-tag--yellow",
    }[status] || "govuk-tag--grey");
  }

  function renderJobStatus(data) {
    const tag = $("job-status-tag");
    if (!tag) return;
    tag.textContent = data.status_label || statusLabel(data.status);
    tag.className = tagClass(data.status);
    tag.dataset.status = data.status || "";
  }

  function renderJobProgress(data) {
    const wrap = $("job-progress");
    if (!wrap) return;
    const progress = data.progress || {};
    wrap.hidden = !progress.visible;
    const label = $("job-progress-label");
    if (label) label.textContent = progress.label || "";
    const pct = Number(progress.pct || 0);
    const fill = $("job-progress-fill");
    if (fill) fill.style.width = pct + "%";
    const bar = $("job-progress-bar");
    if (bar) bar.setAttribute("aria-valuenow", String(pct));
    const step = Number(progress.step || 1);
    wrap.querySelectorAll(".job-steps__item").forEach((li) => {
      const n = Number(li.getAttribute("data-step"));
      const state = n < step ? "done" : n === step ? "current" : "pending";
      li.className = "job-steps__item job-steps__item--" + state;
    });
  }

  function renderActualCost(el, cost) {
    if (!el || !cost) return false;
    if (cost.capped) {
      el.innerHTML = `${cost.label} <span class="govuk-hint">No Anthropic calls (over the routed cap).</span>`;
      return true;
    }
    el.textContent = cost.detail || cost.label;
    return true;
  }

  function colorOf(id) {
    return PALETTE[id] || "#1d70b8";
  }

  function nodeCount(nodes, id) {
    const hit = nodes.find((n) => n.id === id);
    return hit ? Number(hit.n || 0) : 0;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showStage(s, urlsMount) {
    if (!urlsMount || !s) return;
    const termHits = s.term_hits || [];
    const urls = s.urls || [];

    let termBar = "";
    if (termHits.length) {
      const maxN = Math.max(...termHits.map((t) => Number(t.n) || 0), 1);
      const rows = termHits.map((t) => {
        const pct = Math.max(2, (100 * (Number(t.n) || 0)) / maxN);
        return (
          `<tr class="govuk-table__row">`
          + `<th class="govuk-table__header term-rank__term" scope="row">${escapeHtml(t.term)}</th>`
          + `<td class="govuk-table__cell term-rank__cell-bar">`
          + `<span class="term-rank__track" aria-hidden="true">`
          + `<span class="term-rank__bar" style="width:${pct.toFixed(1)}%"></span>`
          + `</span></td>`
          + `<td class="govuk-table__cell govuk-table__cell--numeric term-rank__n">${fmt(t.n)}</td>`
          + `</tr>`
        );
      }).join("");
      termBar =
        `<div class="term-rank">`
        + `<table class="govuk-table">`
        + `<caption class="govuk-table__caption govuk-table__caption--s">Which terms matched</caption>`
        + `<thead class="govuk-table__head"><tr class="govuk-table__row">`
        + `<th class="govuk-table__header">Term</th>`
        + `<th class="govuk-table__header"><span class="govuk-visually-hidden">Share of matches</span></th>`
        + `<th class="govuk-table__header govuk-table__header--numeric">Pages</th>`
        + `</tr></thead>`
        + `<tbody class="govuk-table__body">${rows}</tbody></table>`
        + `<details class="govuk-details">`
        + `<summary class="govuk-details__summary"><span class="govuk-details__summary-text">How matching works</span></summary>`
        + `<div class="govuk-details__text">Original words from your list. Matching is stemmed, so “slurries” on a page shows as slurry. A page can match more than one term, so the counts can add up to more than the shortlist.</div>`
        + `</details></div>`;
    }

    let body = "";
    if (!termHits.length) {
      const rows = urls
        .map((u) => (
          `<li><a class="govuk-link" href="${escapeHtml(u.url)}">${escapeHtml(u.title || u.url)}</a></li>`
        ))
        .join("");
      body = `<ul class="govuk-list">${rows || "<li>None in sample</li>"}</ul>`;
    }

    urlsMount.innerHTML =
      `<h3 class="govuk-heading-s">${escapeHtml(s.label || s.stage || s.id)} (${fmt(s.n)}${s.truncated ? ", sample" : ""})</h3>`
      + (s.meaning ? `<p class="govuk-hint">${escapeHtml(s.meaning)}</p>` : "")
      + termBar
      + body;
  }

  function defaultStage(data) {
    const nodes = (data.sankey && data.sankey.nodes) || [];
    const chips = data.chips || [];
    const items = nodes.concat(chips.map(chipItem));
    return items.find((n) => n.id === "would_route" || n.stage === "would_route")
      || items.find((n) => n.id === "lexicon_hit")
      || items.find((n) => n.id === "pass2_keep")
      || null;
  }

  function storyCardLabel(n) {
    const id = n && n.id;
    if (id === "pass1_true" || id === "pass2_keep" || id === "pass2_unadjudicated") return "Kept";
    if (id === "pass1_false" || id === "pass2_drop") return "Dropped";
    return n.label;
  }

  function storyCard(n, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "funnel-story__card" + (n.hidden ? " funnel-story__card--muted" : "");
    const labelText = storyCardLabel(n);
    btn.setAttribute("aria-label", `${labelText} ${fmt(n.n)}. ${n.meaning || ""}`.trim());

    const bar = document.createElement("span");
    bar.className = "funnel-story__bar";
    bar.style.background = colorOf(n.id);
    bar.setAttribute("aria-hidden", "true");

    const body = document.createElement("span");
    body.className = "funnel-story__body";
    const label = document.createElement("strong");
    label.textContent = labelText;
    const count = document.createElement("span");
    count.className = "funnel-story__count";
    count.textContent = fmt(n.n);
    body.append(label, count);
    if (n.hidden) {
      const note = document.createElement("em");
      note.className = "funnel-story__note";
      note.textContent = "not on diagram";
      body.append(note);
    }

    btn.append(bar, body);
    btn.addEventListener("click", () => onClick(n));
    return btn;
  }

  function chipItem(c) {
    return {
      id: c.stage,
      label: c.label,
      meaning: c.meaning,
      n: c.n,
      urls: c.urls,
      truncated: c.truncated,
      hidden: c.hidden,
      term_hits: c.term_hits,
      stage: c.stage,
    };
  }

  function isLlmFunnel(nodes) {
    return (nodes || []).some((n) => {
      const id = String(n.id || "");
      return id.startsWith("pass1") || id.startsWith("pass2");
    });
  }

  function llmStoryStages(nodes) {
    const hasPass1 = nodes.some((n) => n.id === "pass1_true" || n.id === "pass1_false");
    const hasPass2 = nodes.some(
      (n) => n.id === "pass2_keep" || n.id === "pass2_drop" || n.id === "pass2_unadjudicated",
    );
    return [
      {
        title: "Stage 1: Input Shortlist",
        hint: "Filtered by Organisation, Document Type and Keywords",
        match: (n) => n.id === "lexicon_hit",
      },
      {
        title: "Stage 2: Filtered by LLM Inclusion Rules",
        stats: hasPass1
          ? `Kept ${fmt(nodeCount(nodes, "pass1_true"))} (Dropped ${fmt(nodeCount(nodes, "pass1_false"))})`
          : null,
        hint: "Generous to include as many relevant pages as possible",
        match: (n) => String(n.id || "").startsWith("pass1"),
      },
      {
        title: "Stage 3: Filtered by LLM Exclusion Rules",
        stats: hasPass2
          ? `Kept ${fmt(nodeCount(nodes, "pass2_keep") + nodeCount(nodes, "pass2_unadjudicated"))} (Dropped ${fmt(nodeCount(nodes, "pass2_drop"))})`
          : null,
        hint: "Use rules to exclude irrelevant pages from Stage 2",
        match: (n) => String(n.id || "").startsWith("pass2"),
      },
    ];
  }

  function previewStoryStages(nodes, chips) {
    const ids = new Set(nodes.map((n) => n.id).concat((chips || []).map((c) => c.stage)));
    const stages = [];
    if (ids.has("organisation_pass") || ids.has("organisation_miss")) {
      stages.push({
        title: "Stage 1: Organisation",
        hint: "Published by an organisation you chose",
        match: (n) => n.id === "organisation_pass" || n.id === "organisation_miss",
      });
    }
    if (ids.has("document_type_pass") || ids.has("document_type_miss")) {
      stages.push({
        title: `Stage ${stages.length + 1}: Document type`,
        hint: "The kind of page you asked for",
        match: (n) => n.id === "document_type_pass" || n.id === "document_type_miss",
      });
    }
    if (ids.has("preview_in")) {
      stages.push({
        title: `Stage ${stages.length + 1}: Pages still in play`,
        hint: "After setting aside pages with no topic words",
        match: (n) => n.id === "preview_in",
      });
    }
    const nRoute = nodeCount(nodes, "would_route");
    stages.push({
      title: `Stage ${stages.length + 1}: Keywords`,
      stats: nRoute ? `Would go to the model ${fmt(nRoute)}` : null,
      hint: "Pages that mention a word from your topic list",
      match: (n) => (
        n.id === "would_route" || n.id === "missing_body"
        || n.id === "empty_body" || n.id === "lexicon_miss"
      ),
    });
    return stages;
  }

  function drawStory(sankey, chips, onClick) {
    const nodes = (sankey && sankey.nodes) || [];
    if (!nodes.length && !(chips || []).length) return null;
    const llm = isLlmFunnel(nodes);
    const items = llm
      ? nodes
      : nodes.concat((chips || []).map(chipItem));
    let stages = llm ? llmStoryStages(nodes) : previewStoryStages(nodes, chips);
    if (!llm) stages = stages.filter((s) => items.some(s.match));
    if (!stages.length) return null;

    const root = document.createElement("div");
    root.className = "funnel-story";

    const kicker = document.createElement("h2");
    kicker.className = "govuk-heading-s funnel-story__kicker";
    kicker.textContent = llm
      ? "How we used Inference to filter the pages for relevance"
      : "How we used wordsearch to shortlist pages for inference";
    root.appendChild(kicker);

    const flow = document.createElement("div");
    flow.className = "funnel-story__flow";
    flow.style.setProperty("--funnel-cols", String(Math.max(stages.length, 1)));
    stages.forEach((s) => {
      const col = document.createElement("div");
      col.className = "funnel-story__col";
      const head = document.createElement("div");
      head.className = "funnel-story__col-head";
      const title = document.createElement("strong");
      title.textContent = s.title;
      head.appendChild(title);
      if (s.stats) {
        const stats = document.createElement("strong");
        stats.textContent = s.stats;
        head.appendChild(stats);
      }
      const hint = document.createElement("span");
      hint.textContent = s.hint;
      head.appendChild(hint);
      col.appendChild(head);
      const cards = document.createElement("div");
      cards.className = "funnel-story__cards";
      items.filter(s.match).forEach((n) => cards.appendChild(storyCard(n, onClick)));
      col.appendChild(cards);
      flow.appendChild(col);
    });
    root.appendChild(flow);
    return root;
  }

  function measureSankeyText(text) {
    const ctx = measureSankeyText.ctx || (
      measureSankeyText.ctx = document.createElement("canvas").getContext("2d")
    );
    ctx.font = "13px arial, sans-serif";
    return ctx.measureText(String(text || "")).width;
  }

  function wrapSankeyLabel(text, maxW) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    if (!words.length) return [""];
    const lines = [];
    let line = words[0];
    for (let i = 1; i < words.length; i++) {
      const trial = `${line} ${words[i]}`;
      if (measureSankeyText(trial) <= maxW) {
        line = trial;
      } else {
        lines.push(line);
        line = words[i];
      }
    }
    lines.push(line);
    return lines;
  }

  function fitSankeyViewBox(svg, pad) {
    pad = pad == null ? 10 : pad;
    if (!svg || !svg.isConnected) return;
    let bb;
    try {
      bb = svg.getBBox();
    } catch (_e) {
      return;
    }
    if (!(bb.width > 0) || !(bb.height > 0)) return;
    svg.setAttribute(
      "viewBox",
      `${(bb.x - pad).toFixed(1)} ${(bb.y - pad).toFixed(1)} ${(bb.width + 2 * pad).toFixed(1)} ${(bb.height + 2 * pad).toFixed(1)}`,
    );
  }

  function drawSankey(sankey, onClick) {
    const nodes = sankey.nodes.map((n) => ({ ...n }));
    const links = (sankey.links || []).map((l) => ({ ...l }));
    const nCols = Math.max(...nodes.map((n) => n.column), 0) + 1;
    const nodeW = 18;
    const labelGap = 10;
    const edgePad = 12;
    const padTop = 28;
    const padBot = 28;
    const gap = 18;
    const minH = 16;
    const lineH = 16;
    const maxLineW = 176;
    const labelOnLeft = (n) => n.column === 0 && nCols > 1;

    nodes.forEach((n) => {
      n.lines = wrapSankeyLabel(n.label, maxLineW);
      n.lineW = Math.max(
        measureSankeyText(fmt(n.n)),
        ...n.lines.map((line) => measureSankeyText(line)),
      );
      n.labelH = (n.lines.length + 1) * lineH;
    });

    const leftNeed = Math.max(0, ...nodes.filter(labelOnLeft).map((n) => n.lineW));
    const rightNeed = Math.max(0, ...nodes.filter((n) => !labelOnLeft(n)).map((n) => n.lineW));
    const leftPad = leftNeed + labelGap + edgePad;
    const rightPad = rightNeed + labelGap + edgePad;
    const flowW = Math.max(400, nCols * 170);
    const W = nCols === 1
      ? Math.max(420, leftPad + 80 + rightPad)
      : leftPad + flowW + nodeW + rightPad;

    const byCol = {};
    nodes.forEach((n) => {
      (byCol[n.column] ||= []).push(n);
    });
    const globalMax = Math.max(...nodes.map((n) => n.n || 0), 1);
    const targetInner = nodes.length <= 1 ? 100 : 280;
    Object.values(byCol).forEach((col) => {
      const gaps = Math.max(0, col.length - 1) * gap;
      const barBudget = Math.max(targetInner - gaps, col.length * minH);
      col.forEach((n) => {
        n.h = Math.max(minH, ((n.n || 0) / globalMax) * barBudget);
      });
      const usedBars = col.reduce((a, n) => a + n.h, 0);
      if (usedBars > barBudget) {
        const scale = barBudget / usedBars;
        col.forEach((n) => { n.h *= scale; });
      }
      col.forEach((n) => {
        n.slot = Math.max(n.h, n.labelH);
      });
    });
    const innerH = Math.max(
      targetInner,
      ...Object.values(byCol).map((col) => {
        const gaps = Math.max(0, col.length - 1) * gap;
        return col.reduce((a, n) => a + n.slot, 0) + gaps;
      }),
    );
    const H = padTop + padBot + innerH;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));

    Object.values(byCol).forEach((col) => {
      const gaps = Math.max(0, col.length - 1) * gap;
      const usedSlots = col.reduce((a, n) => a + n.slot, 0);
      let y = padTop + Math.max(0, (innerH - usedSlots - gaps) / 2);
      col.forEach((n) => {
        n.cy = y + n.slot / 2;
        n.y = n.cy - n.h / 2;
        n.x = nCols === 1
          ? W / 2 - nodeW / 2
          : leftPad + n.column * (flowW / Math.max(nCols - 1, 1));
        y += n.slot + gap;
      });
    });

    const srcOff = {};
    const tgtOff = {};
    links.forEach((l) => {
      const s = byId[l.source];
      const t = byId[l.target];
      if (!s || !t) return;
      const sScale = s.h / (s.n || 1);
      const tScale = t.h / (t.n || 1);
      l.sy = s.y + (srcOff[s.id] || 0);
      l.ty = t.y + (tgtOff[t.id] || 0);
      l.sh = l.n * sScale;
      l.th = l.n * tScale;
      srcOff[s.id] = (srcOff[s.id] || 0) + l.sh;
      tgtOff[t.id] = (tgtOff[t.id] || 0) + l.th;
      l.x0 = s.x + nodeW;
      l.x1 = t.x;
      l.color = colorOf(s.id);
    });

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("overflow", "visible");
    svg.setAttribute("class", "sankey");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Filter funnel");

    links.forEach((l) => {
      if (l.x0 == null) return;
      const path = document.createElementNS(ns, "path");
      const mx = (l.x0 + l.x1) / 2;
      path.setAttribute(
        "d",
        `M${l.x0},${l.sy} C${mx},${l.sy} ${mx},${l.ty} ${l.x1},${l.ty}` +
          `L${l.x1},${l.ty + l.th} C${mx},${l.ty + l.th} ${mx},${l.sy + l.sh} ${l.x0},${l.sy + l.sh} Z`,
      );
      path.setAttribute("fill", l.color);
      path.setAttribute("class", "sankey-link");
      svg.appendChild(path);
    });

    nodes.forEach((n) => {
      const g = document.createElementNS(ns, "g");
      g.setAttribute("class", "sankey-node");
      g.setAttribute("tabindex", "0");
      g.setAttribute("role", "button");
      g.setAttribute("aria-label", `${n.label} ${fmt(n.n)}`);

      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", n.x);
      rect.setAttribute("y", n.y);
      rect.setAttribute("width", nodeW);
      rect.setAttribute("height", Math.max(n.h, 1));
      rect.setAttribute("rx", "3");
      rect.setAttribute("fill", colorOf(n.id));
      g.appendChild(rect);

      const onLeft = labelOnLeft(n);
      const text = document.createElementNS(ns, "text");
      const tx = onLeft ? n.x - labelGap : n.x + nodeW + labelGap;
      const lines = n.lines.length ? n.lines : [n.label];
      text.setAttribute("x", tx);
      text.setAttribute("y", n.cy);
      text.setAttribute("text-anchor", onLeft ? "end" : "start");
      text.setAttribute("class", "sankey-label");
      lines.concat([fmt(n.n)]).forEach((line, i) => {
        const tspan = document.createElementNS(ns, "tspan");
        tspan.setAttribute("x", tx);
        tspan.setAttribute("dy", i === 0 ? `${-((lines.length) / 2) * 1.25}em` : "1.25em");
        if (i === lines.length) tspan.setAttribute("class", "sankey-count");
        tspan.textContent = line;
        text.appendChild(tspan);
      });
      g.appendChild(text);

      const activate = () => onClick(n);
      g.addEventListener("click", activate);
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activate();
        }
      });
      svg.appendChild(g);
    });
    requestAnimationFrame(() => fitSankeyViewBox(svg));
    return svg;
  }

  function renderFunnel(payload, mount, urlsMount) {
    const data = payload && payload.sankey ? payload : { stages: payload, sankey: null, chips: [] };
    mount.innerHTML = "";
    mount.className = "funnel";

    if (data.caption) {
      const p = document.createElement("p");
      p.className = "funnel-caption";
      p.textContent = data.caption;
      mount.appendChild(p);
    }

    const llm = isLlmFunnel((data.sankey && data.sankey.nodes) || []);
    const storyChips = llm ? [] : (data.chips || []);
    if (data.sankey && (data.sankey.nodes || []).length) {
      const story = drawStory(data.sankey, storyChips, (node) => showStage(node, urlsMount));
      if (story) mount.appendChild(story);
    }

    if (llm && (data.chips || []).length) {
      const row = document.createElement("div");
      row.className = "funnel-chips";
      data.chips.forEach((c) => {
        row.appendChild(storyCard(chipItem(c), () => showStage(c, urlsMount)));
      });
      mount.appendChild(row);
    }

    if (data.sankey && (data.sankey.nodes || []).length) {
      const wrap = document.createElement("div");
      wrap.className = "sankey-wrap";
      wrap.appendChild(drawSankey(data.sankey, (node) => showStage(node, urlsMount)));
      mount.appendChild(wrap);
    }

    const hasDiagram = (data.sankey && (data.sankey.nodes || []).length)
      || (data.chips || []).length;
    if (hasDiagram) {
      const hint = document.createElement("p");
      hint.className = "govuk-hint";
      hint.textContent = "Click a coloured box for example pages. The diagram follows pages left to right. Pages with no topic words are off it — there are too many of them.";
      mount.appendChild(hint);
    }

    const pick = defaultStage(data);
    if (pick && urlsMount) showStage(pick, urlsMount);
  }

  const select = $("template-select");
  const templates = window.GRF_TEMPLATES || (function () {
    const el = $("templates-data");
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (_e) { return null; }
  })();
  if (select && templates) {
    select.addEventListener("change", () => {
      const t = templates[select.value];
      if (!t) return;
      $("name").value = t.name;
      $("description").value = t.description;
      $("exclusion_criteria").value = t.exclusion_criteria;
      $("keep_hints").value = t.keep_hints;
      $("drop_hints").value = t.drop_hints;
      $("lexicon").value = t.lexicon;
      if ($("organisations")) setCheckedValues("organisations", t.organisations || []);
      setCheckedValues("document_types", t.document_types || []);
    });
  }

  const PHASE_LABEL = {
    scan: "Scanning page bodies",
    stem: "Indexing page text (once per corpus)",
    wordsearch: "Matching lexicon",
  };

  function progressPct(phase, done, total) {
    const p = total ? done / total : 1;
    if (phase === "scan") return Math.round(p * 8);
    if (phase === "stem") return Math.round(8 + p * 72);
    return Math.round(80 + p * 20);
  }

  function setPreviewProgress(phase, done, total) {
    const wrap = $("preview-progress");
    const bar = $("preview-progress-bar");
    const fill = $("preview-progress-fill");
    const label = $("preview-progress-label");
    if (!wrap || !bar || !fill || !label) return;
    wrap.hidden = false;
    const pct = Math.max(0, Math.min(100, progressPct(phase, done, total)));
    fill.style.width = pct + "%";
    bar.setAttribute("aria-valuenow", String(pct));
    const name = PHASE_LABEL[phase] || "Working";
    label.textContent = total
      ? `${name} — ${fmt(done)} / ${fmt(total)}`
      : name + "…";
  }

  function hidePreviewProgress() {
    const wrap = $("preview-progress");
    if (wrap) wrap.hidden = true;
  }

  async function readNdjson(res, onEvent) {
    if (!res.body) {
      const text = await res.text();
      text.split("\n").filter(Boolean).forEach((line) => onEvent(JSON.parse(line)));
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (line.trim()) onEvent(JSON.parse(line));
      }
    }
    if (buf.trim()) onEvent(JSON.parse(buf));
  }

  function fieldForError(msg) {
    const m = String(msg || "").toLowerCase();
    if (m.includes("email")) return "email";
    if (m.includes("slug") || m.includes("name must")) return "name";
    if (m.includes("unknown corpus")) return "corpus_id";
    if (m.includes("what to include") || m.includes("description")) return "description";
    if (m.includes("what to exclude") || m.includes("exclusion")) return "exclusion_criteria";
    if (m.includes("keyword") || m.includes("lexicon")) return "lexicon";
    return null;
  }

  function showTab(id) {
    const link = document.querySelector(`.govuk-tabs__tab[href="#${id}"]`);
    if (link) link.click();
  }

  function setPreviewButtonsDisabled(disabled) {
    ["preview-btn", "preview-again-btn"].forEach((id) => {
      const btn = $(id);
      if (btn) btn.disabled = disabled;
    });
  }

  function clearFormError() {
    const box = $("form-error");
    if (box) box.hidden = true;
    document.querySelectorAll(".govuk-form-group--error").forEach((el) => {
      el.classList.remove("govuk-form-group--error");
    });
    document.querySelectorAll(".govuk-input--error, .govuk-textarea--error").forEach((el) => {
      el.classList.remove("govuk-input--error", "govuk-textarea--error");
    });
    document.querySelectorAll("[data-grf-error]").forEach((el) => el.remove());
  }

  function showFormError(msg) {
    const box = $("form-error");
    const link = $("form-error-link");
    if (!box || !link) return;
    const field = fieldForError(msg);
    link.textContent = msg;
    if (field) {
      link.setAttribute("href", "#" + field);
      showTab("definition");
    } else {
      link.setAttribute("href", "#preview-run");
      showTab("preview-run");
    }
    box.hidden = false;
    if (field) {
      const group = $("group-" + field);
      const input = $(field);
      if (group) group.classList.add("govuk-form-group--error");
      if (input && (input.tagName === "INPUT" || input.tagName === "TEXTAREA" || input.tagName === "SELECT")) {
        input.classList.add(input.tagName === "TEXTAREA" ? "govuk-textarea--error" : "govuk-input--error");
        let fieldErr = $(field + "-error");
        if (!fieldErr) {
          fieldErr = document.createElement("p");
          fieldErr.id = field + "-error";
          fieldErr.className = "govuk-error-message";
          fieldErr.setAttribute("data-grf-error", "");
          fieldErr.innerHTML = '<span class="govuk-visually-hidden">Error:</span> <span></span>';
          input.insertAdjacentElement("beforebegin", fieldErr);
        }
        fieldErr.querySelector("span:last-child").textContent = msg;
      }
    }
    box.scrollIntoView({ block: "start" });
  }

  const form = $("wizard");
  let previewId = null;

  async function runPreview() {
    clearFormError();
    setPreviewButtonsDisabled(true);
    try {
      const res = await fetch("/preview", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/x-ndjson",
        },
        body: JSON.stringify(fields()),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || res.statusText);
      }
      showTab("preview-run");
      const empty = $("preview-empty");
      if (empty) empty.hidden = true;
      const panel = $("preview-panel");
      if (panel) panel.hidden = false;
      const nPages = document.body.dataset.nPages;
      $("preview-cap").className = "govuk-body";
      $("preview-cap").textContent = "";
      costEstimates = { batch: null, sync: null };
      showCostEstimate($("preview-cost"), null);
      $("preview-warnings").innerHTML = "";
      $("funnel").innerHTML = "";
      const urlsEl = $("funnel-urls");
      if (urlsEl) urlsEl.innerHTML = "";
      setPreviewProgress("scan", 0, Number(nPages) || 0);
      let data = null;
      await readNdjson(res, (ev) => {
        if (ev.event === "progress") {
          setPreviewProgress(ev.phase, ev.done, ev.total);
        } else if (ev.event === "error") {
          throw new Error(ev.detail || "Preview failed");
        } else if (ev.event === "done") {
          data = ev;
        }
      });
      if (!data) throw new Error("Preview ended without a result");
      hidePreviewProgress();
      previewId = data.preview_id;
      const capOk = data.cap.ok && data.daily.ok;
      const c = data.counts;
      const scoped = c.organisation_filter || c.document_type_filter;
      const routed = scoped
        ? `${fmt(c.would_route)} of ${fmt(c.input_pages)} in-scope pages would go to the model (${fmt(c.corpus_pages)} on the index)`
        : `${fmt(c.would_route)} pages would go to the model`;
      const daily = `daily ${fmt(data.daily.used)} + ${fmt(c.would_route)} / ${fmt(data.daily.max)}`;
      let capNote = `(run cap ${fmt(data.cap.max_routed)}; ${daily}).`;
      if (!data.cap.ok) {
        capNote =
          `Over the run cap of ${fmt(data.cap.max_routed)} — wordsearch is complete (not truncated); Run filter is blocked. ${daily}.`;
      } else if (!data.daily.ok) {
        capNote =
          `Would exceed today's routed budget (${fmt(data.daily.used)} + ${fmt(c.would_route)} / ${fmt(data.daily.max)}). Run filter is blocked. Run cap ${fmt(data.cap.max_routed)}.`;
      }
      $("preview-cap").textContent =
        `${routed} ` +
        capNote +
        (data.cached ? " Reused the previous wordsearch for this lexicon + index." : "");
      $("preview-cap").className = capOk ? "govuk-body" : "govuk-error-message";
      costEstimates.batch = data.cost_estimate;
      costEstimates.sync = data.cost_estimate_sync;
      showSelectedCostEstimate();
      $("preview-warnings").innerHTML = (data.warnings || [])
        .map((w) => `<li>${w}</li>`)
        .join("");
      renderFunnel(data, $("funnel"), $("funnel-urls"));
      $("submit-btn").disabled = !capOk;
    } catch (e) {
      hidePreviewProgress();
      showFormError(e.message);
      $("submit-btn").disabled = true;
    } finally {
      setPreviewButtonsDisabled(false);
    }
  }

  if ($("preview-btn")) $("preview-btn").addEventListener("click", runPreview);
  if ($("preview-again-btn")) $("preview-again-btn").addEventListener("click", runPreview);
  if ($("corpus_id")) {
    $("corpus_id").addEventListener("change", () => {
      previewId = null;
      if ($("submit-btn")) $("submit-btn").disabled = true;
      applySnapshotScope($("corpus_id").value);
    });
  }
  const errLink = $("form-error-link");
  if (errLink) {
    errLink.addEventListener("click", () => {
      const href = errLink.getAttribute("href") || "";
      if (href.startsWith("#") && href !== "#preview-run" && href !== "#results") {
        showTab("definition");
      }
    });
  }

  if (form) {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      clearFormError();
      if (!previewId) {
        showFormError("Run Preview first.");
        return;
      }
      const res = await fetch("/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preview_id: previewId,
          email: $("email").value,
          llm_mode: selectedLlmMode(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        showFormError(data.detail || res.statusText);
        return;
      }
      window.location = `/jobs/${data.id}#results`;
    });
  }

  if (window.GRF_JOB_ID) {
    const funnel = $("job-funnel");
    const urls = $("job-funnel-urls");
    if (window.GRF_FUNNEL && (window.GRF_FUNNEL.sankey || window.GRF_FUNNEL.stages)) {
      renderFunnel(window.GRF_FUNNEL, funnel, urls);
    }
    const poll = async () => {
      const res = await fetch(`/api/jobs/${window.GRF_JOB_ID}`);
      if (!res.ok) return;
      const data = await res.json();
      renderJobStatus(data);
      renderJobProgress(data);
      const logEl = $("job-log");
      if (logEl) logEl.textContent = (data.log_tail || []).join("\n");
      const costEl = $("job-cost");
      if (costEl && !renderActualCost(costEl, data.cost)) {
        showCostEstimate(costEl, data.cost_estimate);
      }
      const dur = $("job-duration");
      if (dur) {
        if (data.duration && data.duration.label) {
          const hint = (data.duration.llm_label && data.duration.source !== "llm")
            ? ` <span class="govuk-hint">LLM ${data.duration.llm_label}</span>`
            : "";
          dur.innerHTML = data.duration.label + hint;
        } else {
          dur.textContent = "—";
        }
      }
      if (data.funnel && (data.funnel.sankey || data.funnel.stages)) {
        renderFunnel(data.funnel, funnel, urls);
      }
      if (data.status === "queued" || data.status === "running") {
        setTimeout(poll, 4000);
      } else if (!$("job-status-tag").closest("main").querySelector(".upload")) {
        window.location.reload();
      }
    };
    if (["queued", "running"].includes(($("job-status-tag") || {}).dataset?.status)) {
      setTimeout(poll, 4000);
    }
  }

  initFilterableCheckboxes({
    filterId: "organisations-filter",
    listId: "organisations-list",
    metaId: "organisations-meta",
    selectedId: "organisations-selected",
    name: "organisations",
    noun: "organisations",
  });
})();
