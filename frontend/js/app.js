(function () {
  const NS = "http://www.w3.org/2000/svg";
  const W = 500, H = 400, M = 50;
  const MAX = 100; // axis range for both price and quantity

  const x = (q) => M + (q / MAX) * (W - 2 * M);
  const y = (p) => H - M - (p / MAX) * (H - 2 * M);
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  // Demand: P = dA - SLOPE*Q ; supply: P = sA + SLOPE*Q.
  // Dragging a handle shifts its curve by changing the intercept.
  const SLOPE = 0.8;
  const HANDLE_Q = 20;
  const initial = { dA: 90, sA: 10 };
  const state = { ...initial };

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  document.getElementById("graph").appendChild(svg);

  function el(name, attrs) {
    const e = document.createElementNS(NS, name);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    svg.appendChild(e);
    return e;
  }

  el("line", { x1: M, y1: H - M, x2: W - M, y2: H - M, stroke: "#333" });
  el("line", { x1: M, y1: M, x2: M, y2: H - M, stroke: "#333" });
  el("text", { x: W / 2, y: H - 12, "text-anchor": "middle" }).textContent = "Quantity";
  el("text", { x: 14, y: H / 2, "text-anchor": "middle", transform: `rotate(-90 14 ${H / 2})` }).textContent = "Price";

  const demand = el("line", { stroke: "#c0392b", "stroke-width": 3 });
  const supply = el("line", { stroke: "#2471a3", "stroke-width": 3 });
  const dText = el("text", { fill: "#c0392b", "font-weight": "bold" });
  const sText = el("text", { fill: "#2471a3", "font-weight": "bold" });
  dText.textContent = "D";
  sText.textContent = "S";
  const vLine = el("line", { stroke: "#888", "stroke-dasharray": "4" });
  const hLine = el("line", { stroke: "#888", "stroke-dasharray": "4" });
  const eqDot = el("circle", { r: 6, fill: "#27ae60" });
  const dHandle = el("circle", { r: 10, fill: "#c0392b", class: "handle" });
  const sHandle = el("circle", { r: 10, fill: "#2471a3", class: "handle" });

  function setLine(line, q1, p1, q2, p2) {
    line.setAttribute("x1", x(q1)); line.setAttribute("y1", y(p1));
    line.setAttribute("x2", x(q2)); line.setAttribute("y2", y(p2));
  }

  function render() {
    const dQ = Math.min(state.dA / SLOPE, MAX);
    setLine(demand, 0, state.dA, dQ, state.dA - SLOPE * dQ);
    const sQ = Math.min((MAX - state.sA) / SLOPE, MAX);
    setLine(supply, 0, state.sA, sQ, state.sA + SLOPE * sQ);

    dHandle.setAttribute("cx", x(HANDLE_Q)); dHandle.setAttribute("cy", y(state.dA - SLOPE * HANDLE_Q));
    sHandle.setAttribute("cx", x(HANDLE_Q)); sHandle.setAttribute("cy", y(state.sA + SLOPE * HANDLE_Q));
    dText.setAttribute("x", x(0) + 8); dText.setAttribute("y", y(state.dA) - 8);
    sText.setAttribute("x", x(sQ) - 16); sText.setAttribute("y", y(state.sA + SLOPE * sQ) - 8);

    const q = (state.dA - state.sA) / (2 * SLOPE);
    const p = state.dA - SLOPE * q;
    const valid = q >= 0 && p >= 0 && q <= MAX && p <= MAX;
    for (const e of [eqDot, vLine, hLine]) e.style.display = valid ? "" : "none";
    if (valid) {
      eqDot.setAttribute("cx", x(q)); eqDot.setAttribute("cy", y(p));
      setLine(vLine, q, p, q, 0);
      setLine(hLine, 0, p, q, p);
    }
    document.getElementById("readout").textContent = valid
      ? `Equilibrium: Q* = ${q.toFixed(1)}, P* = ${p.toFixed(1)}`
      : "No positive equilibrium for these curves.";
  }

  function pointerPrice(evt) {
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const p = pt.matrixTransform(svg.getScreenCTM().inverse());
    return ((H - M - p.y) / (H - 2 * M)) * MAX;
  }

  // sign: -1 for demand (downward slope), +1 for supply.
  function makeDraggable(handle, key, sign) {
    handle.addEventListener("pointerdown", (evt) => {
      handle.setPointerCapture(evt.pointerId);
      handle.style.cursor = "grabbing";
      const move = (e) => {
        state[key] = clamp(pointerPrice(e) - sign * SLOPE * HANDLE_Q, 0, MAX);
        render();
      };
      const up = () => {
        handle.style.cursor = "";
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", up);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
      handle.addEventListener("pointercancel", up);
    });
  }

  makeDraggable(dHandle, "dA", -1);
  makeDraggable(sHandle, "sA", 1);

  document.getElementById("reset").addEventListener("click", () => {
    Object.assign(state, initial);
    render();
  });

  render();
})();
