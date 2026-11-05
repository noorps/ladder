// node harness for the python cross-check: reads the grid spec as json on argv[2] (or stdin)
// and prints the js simulator's throughput for every cell.
const sim = require("./sim.js");
const fs = require("fs");
const spec = JSON.parse(process.argv[2] || fs.readFileSync(0, "utf8"));
const out = spec.grid.map(cell => {
  const r = sim.simulate(spec.loads, cell.cv, cell.buffer, spec.seed, spec.warmup, spec.units);
  return { cv: cell.cv, buffer: cell.buffer, throughput: r.throughput, utilization: r.stations.map(s => s.busy) };
});
process.stdout.write(JSON.stringify(out));
