import { useEffect, useState } from "react";
import { api, type Concept, type Experiment } from "./api";
import { Chart, type ChartSeries } from "./Chart";
import { formatDay, formatIntensity, formatWhen } from "./format";

const COLORS = ["#8d3d32", "#2f4f45", "#2c4c72", "#8a5a2b", "#5a3e6b", "#3e5c58", "#6e4b3a"];

type Route =
  | { name: "trajectory" }
  | { name: "day"; day: string }
  | { name: "taxonomy"; id?: string }
  | { name: "evidence"; id: string }
  | { name: "settings" };

export function App() {
  const [route, setRoute] = useState<Route>(readRoute());
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [experimentId, setExperimentId] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const onHash = () => setRoute(readRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    Promise.all([api.experiments(), api.concepts()])
      .then(([experimentBody, conceptBody]) => {
        setExperiments(experimentBody.experiments);
        setConcepts(conceptBody.concepts);
        setExperimentId((current) => current || experimentBody.experiments.at(-1)?.id || "");
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load Serah"));
  }, []);

  const experiment = experiments.find((item) => item.id === experimentId) ?? null;

  return (
    <div className="app">
      <aside className="rail">
        <p className="brand">
          Serah
          <span>Observatory</span>
        </p>
        <nav>
          <a className={route.name === "trajectory" ? "active" : ""} href="#/trajectory">Trajectory</a>
          <a className={route.name === "day" ? "active" : ""} href="#/day">Selected day</a>
          <a className={route.name === "taxonomy" ? "active" : ""} href="#/taxonomy">Taxonomy</a>
          <a className={route.name === "settings" ? "active" : ""} href="#/settings">Replay settings</a>
        </nav>
      </aside>
      <main className="stage">
        <p className="kicker">Experimental derived intensities. Not a clinical measure.</p>
        {error && <p className="error">{error}</p>}
        {experiments.length === 0 && !error && (
          <p className="note">No experiment is stored yet. From the repository, run <code>serah demo</code> and refresh.</p>
        )}
        {route.name === "trajectory" && (
          <Trajectory
            concepts={concepts}
            experiment={experiment}
            experiments={experiments}
            onExperiment={setExperimentId}
          />
        )}
        {route.name === "day" && <DayView experiment={experiment} concepts={concepts} initialDay={route.day} />}
        {route.name === "taxonomy" && <Taxonomy concepts={concepts} selected={route.id} onChange={setConcepts} />}
        {route.name === "evidence" && <Evidence observationId={route.id} experimentId={experimentId} />}
        {route.name === "settings" && (
          <Settings
            experiment={experiment}
            experiments={experiments}
            onCreated={(id) => {
              setExperimentId(id);
              api.experiments().then((body) => setExperiments(body.experiments));
            }}
          />
        )}
      </main>
    </div>
  );
}

function Trajectory({
  concepts,
  experiment,
  experiments,
  onExperiment,
}: {
  concepts: Concept[];
  experiment: Experiment | null;
  experiments: Experiment[];
  onExperiment: (id: string) => void;
}) {
  const [conceptId, setConceptId] = useState("emotion.anger");
  const [mode, setMode] = useState<"raw" | "reservoir">("reservoir");
  const [view, setView] = useState<"engines" | "emotions">("engines");
  const [enginesOn, setEnginesOn] = useState<string[]>([]);
  const [emotionIds, setEmotionIds] = useState<string[]>(["emotion.anger", "emotion.fear", "emotion.gratitude", "emotion.hope"]);
  const [density, setDensity] = useState(false);
  const [series, setSeries] = useState<ChartSeries[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (experiment) {
      setEnginesOn(experiment.engines);
    }
  }, [experiment]);

  useEffect(() => {
    if (!experiment) {
      return;
    }
    const request =
      view === "engines"
        ? api.series(experiment.id, conceptId, mode)
        : api.compare(experiment.id, enginesOn[0] || experiment.engines[0], emotionIds, mode);
    request
      .then((body) => {
        const lines = body.series
          .filter((line) => (view === "engines" ? enginesOn.includes(line.engine_id || "") : true))
          .map((line, index) => ({
            id: line.engine_id || line.concept_id || String(index),
            label: labelFor(line.engine_id || line.concept_id || "", concepts),
            color: COLORS[index % COLORS.length],
            points: line.points,
          }));
        setSeries(lines);
        setMessage(lines.every((line) => line.points.length === 0) ? "No points for this selection." : "");
      })
      .catch((reason: unknown) => setMessage(reason instanceof Error ? reason.message : "Could not load the series"));
  }, [experiment, conceptId, mode, view, enginesOn, emotionIds, concepts]);

  return (
    <section>
      <h1>{view === "engines" ? "One concept, several engines" : "One engine, several concepts"}</h1>
      <p className="note">
        Raw observations are what an engine returned. Reservoirs are the shared decay model applied afterwards.
        Open circles are days with no new observation.
      </p>
      <div className="controls">
        <label>
          Experiment
          <select value={experiment?.id || ""} onChange={(event) => onExperiment(event.target.value)}>
            {experiments.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.half_life_hours}h {item.decay_type}
              </option>
            ))}
          </select>
        </label>
        <label>
          View
          <select value={view} onChange={(event) => setView(event.target.value as "engines" | "emotions")}>
            <option value="engines">One concept, many engines</option>
            <option value="emotions">One engine, many concepts</option>
          </select>
        </label>
        <label>
          Graph
          <select value={mode} onChange={(event) => setMode(event.target.value as "raw" | "reservoir")}>
            <option value="reservoir">Temporal reservoirs</option>
            <option value="raw">Raw observations</option>
          </select>
        </label>
        {view === "engines" && (
          <label>
            Concept
            <select value={conceptId} onChange={(event) => setConceptId(event.target.value)}>
              {concepts.map((concept) => (
                <option key={concept.id} value={concept.id}>
                  {concept.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Evidence density
          <input type="checkbox" checked={density} onChange={(event) => setDensity(event.target.checked)} />
        </label>
      </div>
      {view === "engines" && (
        <div className="row">
          {experiment?.engines.map((engine) => (
            <label key={engine}>
              <input
                type="checkbox"
                checked={enginesOn.includes(engine)}
                onChange={(event) =>
                  setEnginesOn((current) =>
                    event.target.checked ? [...current, engine] : current.filter((item) => item !== engine),
                  )
                }
              />
              {labelFor(engine, concepts)}
            </label>
          ))}
        </div>
      )}
      {view === "emotions" && (
        <div className="row">
          {concepts.filter((concept) => concept.status === "active").map((concept) => (
            <label key={concept.id}>
              <input
                type="checkbox"
                checked={emotionIds.includes(concept.id)}
                onChange={(event) =>
                  setEmotionIds((current) =>
                    event.target.checked ? [...current, concept.id] : current.filter((item) => item !== concept.id),
                  )
                }
              />
              {concept.name}
            </label>
          ))}
        </div>
      )}
      {message && <p className="muted">{message}</p>}
      <div className="card">
        <Chart
          series={series}
          mode={mode}
          showDensity={density}
          onSelect={(point) => {
            if (point.observation_id) {
              window.location.hash = `#/evidence/${point.observation_id}`;
            } else {
              window.location.hash = `#/day/${point.t.slice(0, 10)}`;
            }
          }}
        />
      </div>
    </section>
  );
}

function DayView({
  experiment,
  concepts,
  initialDay,
}: {
  experiment: Experiment | null;
  concepts: Concept[];
  initialDay: string;
}) {
  const [day, setDay] = useState(initialDay || "2024-03-03");
  const [engine, setEngine] = useState(experiment?.engines[0] || "mock");

  useEffect(() => {
    if (initialDay) {
      setDay(initialDay);
    }
  }, [initialDay]);
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (experiment && !experiment.engines.includes(engine)) {
      setEngine(experiment.engines[0]);
    }
  }, [experiment, engine]);

  useEffect(() => {
    if (!experiment) {
      return;
    }
    api.day(day, experiment.id, engine).then(setPayload).catch(() => setPayload(null));
  }, [experiment, day, engine]);

  const states = (payload?.states as { concept_id: string; name: string; level: number; observed: boolean }[]) || [];
  const observations =
    (payload?.observations as { observation_id: string; name: string; expected_intensity: number; excerpt: string }[]) ||
    [];
  const episodes = (payload?.episodes as { episode_id: string; timestamp: string; excerpt: string }[]) || [];

  return (
    <section>
      <h1>{formatDay(day)}</h1>
      <p className="note">Reservoir levels for the selected engine at the end of this UTC day. Bars are not a diagnosis.</p>
      <div className="controls">
        <label>
          Day
          <input value={day} onChange={(event) => setDay(event.target.value)} />
        </label>
        <label>
          Engine
          <select value={engine} onChange={(event) => setEngine(event.target.value)}>
            {(experiment?.engines || []).map((item) => (
              <option key={item} value={item}>
                {labelFor(item, concepts)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="bars">
        {states.map((state) => (
          <div className="bar-row" key={state.concept_id}>
            <span>{state.name}</span>
            <div className="bar">
              <span style={{ width: `${Math.max(0, Math.min(100, state.level))}%` }} />
            </div>
            <span className="num">{formatIntensity(state.level)}</span>
          </div>
        ))}
        {states.length === 0 && <p className="muted">No reservoir on this day for this engine.</p>}
      </div>
      <h2>Observations</h2>
      <div className="list">
        {observations.map((item) => (
          <a className="item" key={item.observation_id} href={`#/evidence/${item.observation_id}`}>
            {item.name} · raw {formatIntensity(item.expected_intensity)}
            <div className="muted">{item.excerpt}</div>
          </a>
        ))}
        {observations.length === 0 && <p className="muted">No observation was stored. That is not a score of zero.</p>}
      </div>
      <h2>Episodes</h2>
      <div className="list">
        {episodes.map((episode) => (
          <div className="item" key={episode.episode_id}>
            <div className="muted">{formatWhen(episode.timestamp)}</div>
            {episode.excerpt}
          </div>
        ))}
      </div>
    </section>
  );
}

function Taxonomy({
  concepts,
  selected,
  onChange,
}: {
  concepts: Concept[];
  selected?: string;
  onChange: (concepts: Concept[]) => void;
}) {
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const shown = concepts.filter((concept) => filter === "all" || concept.status === filter || (filter === "locked" && concept.locked));

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    api.concept(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected]);

  async function activate(id: string, status: string) {
    await api.setStatus(id, status, new Date().toISOString().slice(0, 10), "Set from the taxonomy view");
    onChange((await api.concepts()).concepts);
    setDetail(await api.concept(id));
  }

  if (detail) {
    const history = (detail.history as { event_type: string; effective_on: string; rationale: string }[]) || [];
    const episodes = (detail.episodes as { episode_id: string; timestamp: string; excerpt: string }[]) || [];
    const relationships = (detail.relationships as { relation: string; source: string; target: string; confidence: number }[]) || [];
    return (
      <section>
        <p><a href="#/taxonomy">All concepts</a></p>
        <h1>{String(detail.name)}</h1>
        <p className="muted">
          {String(detail.family)} · {String(detail.status)} · version {String(detail.version)} · support days {String(detail.support_count)}
          {detail.locked ? " · locked core" : ""}
        </p>
        <p>{String(detail.definition)}</p>
        <p className="muted">Include when {String(detail.inclusion)}</p>
        <p className="muted">Leave out when {String(detail.exclusion)}</p>
        {!detail.locked && detail.status !== "active" && (
          <button type="button" onClick={() => activate(String(detail.id), "active")}>Activate</button>
        )}
        {!detail.locked && detail.status !== "rejected" && (
          <button className="ghost" type="button" onClick={() => activate(String(detail.id), "rejected")}>Reject</button>
        )}
        <h2>Relationships</h2>
        <ul>
          {relationships.map((item) => (
            <li key={`${item.source}-${item.relation}-${item.target}`}>
              {item.source} {item.relation} {item.target} ({item.confidence})
            </li>
          ))}
        </ul>
        <h2>History</h2>
        <ul>
          {history.map((event, index) => (
            <li key={`${event.event_type}-${index}`}>
              {event.effective_on} · {event.event_type} · {event.rationale}
            </li>
          ))}
        </ul>
        <h2>Supporting episodes</h2>
        <div className="list">
          {episodes.map((episode) => (
            <div className="item" key={episode.episode_id}>
              <div className="muted">{formatWhen(episode.timestamp)}</div>
              {episode.excerpt}
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section>
      <h1>Taxonomy</h1>
      <div className="controls">
        <label>
          Show
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All</option>
            <option value="locked">Locked core</option>
            <option value="active">Active</option>
            <option value="candidate">Candidates</option>
            <option value="proposed">Proposed</option>
            <option value="dormant">Dormant</option>
            <option value="rejected">Rejected</option>
            <option value="deprecated">Deprecated</option>
          </select>
        </label>
      </div>
      <div className="list">
        {shown.map((concept) => (
          <a className="item" key={concept.id} href={`#/taxonomy/${concept.id}`}>
            {concept.name}
            <div className="muted">
              {concept.family} · {concept.status}
              {concept.locked ? " · locked" : ""} · v{concept.version}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

function Evidence({ observationId, experimentId }: { observationId: string; experimentId: string }) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (!experimentId) {
      return;
    }
    api.observation(observationId, experimentId).then(setPayload).catch(() => setPayload(null));
  }, [observationId, experimentId]);
  if (!payload) {
    return <p className="muted">Loading the observation.</p>;
  }
  const observation = payload.observation as Record<string, unknown>;
  const episode = payload.episode as Record<string, unknown> | null;
  const concept = payload.concept as Record<string, unknown>;
  const messages = (payload.messages as { role: string; role_in_episode: string; text: string }[]) || [];
  const distribution = (observation.distribution as Record<string, number> | null) || null;
  return (
    <section>
      <h1>{String(concept.name)}</h1>
      <p className="muted">
        {String(observation.engine_id)} · question v{String(observation.question_version)} · concept v
        {String(observation.concept_version)} · {String(observation.native_output_type)}
      </p>
      <p className="quote">Derived intensity {formatIntensity(observation.expected_intensity as number)}</p>
      <p className="note">{String(concept.definition)}</p>
      {episode && (
        <>
          <h2>User evidence</h2>
          <p className="quote">{String(episode.user_text)}</p>
          {episode.context_text ? (
            <>
              <h2>Context, not evidence</h2>
              <p className="muted">{String(episode.context_text)}</p>
            </>
          ) : null}
        </>
      )}
      <h2>Messages</h2>
      <div className="list">
        {messages.map((message) => (
          <div className="item" key={`${message.role}-${message.role_in_episode}-${message.text.slice(0, 24)}`}>
            <div className="muted">{message.role} · {message.role_in_episode}</div>
            {message.text}
          </div>
        ))}
      </div>
      {distribution && (
        <>
          <h2>Stored distribution</h2>
          <p className="muted">
            {Object.entries(distribution)
              .map(([bin, mass]) => `${bin}: ${Number(mass).toFixed(3)}`)
              .join("  ·  ")}
          </p>
        </>
      )}
    </section>
  );
}

function Settings({
  experiment,
  experiments,
  onCreated,
}: {
  experiment: Experiment | null;
  experiments: Experiment[];
  onCreated: (id: string) => void;
}) {
  const [halfLife, setHalfLife] = useState(experiment?.half_life_hours ?? 72);
  const [decay, setDecay] = useState(experiment?.decay_type ?? "exponential");
  const [gain, setGain] = useState(experiment?.activation_gain ?? 0.35);
  const [engines, setEngines] = useState<string[]>(experiment?.engines ?? ["mock", "mock_conservative"]);
  const [models, setModels] = useState<{ engine_id: string; availability: string; detail: string }[]>([]);
  const [observedEngines, setObservedEngines] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [day, setDay] = useState("2024-03-03");
  const [annotation, setAnnotation] = useState("");

  useEffect(() => {
    api.models().then((body) => setModels(body.engines)).catch(() => setModels([]));
    api.status().then((body) => setObservedEngines(Object.keys(body.observations || {}))).catch(() => setObservedEngines([]));
  }, []);

  async function replay() {
    if (!experiment) {
      return;
    }
    const created = await api.createExperiment({
      name: `${experiment.name} / ${halfLife}h ${decay}`,
      engines,
      decay_type: decay,
      half_life_hours: Number(halfLife),
      activation_gain: Number(gain),
      reservoir_update: experiment.reservoir_update,
      core_scoring_mode: experiment.core_scoring_mode,
      notes: "Created from the replay settings. Observations were not recomputed.",
    });
    await api.replay(created.id);
    onCreated(created.id);
    window.location.hash = "#/trajectory";
  }

  return (
    <section>
      <h1>Replay settings</h1>
      <p className="note">
        Changing decay builds a new experiment from the observations already stored. It does not call a model.
        The previous trajectory stays available in the experiment list.
      </p>
      <div className="controls">
        <label>
          Half-life hours
          <input type="number" value={halfLife} min={1} onChange={(event) => setHalfLife(Number(event.target.value))} />
        </label>
        <label>
          Decay
          <select value={decay} onChange={(event) => setDecay(event.target.value)}>
            <option value="exponential">Exponential</option>
            <option value="linear">Linear</option>
            <option value="none">None</option>
          </select>
        </label>
        <label>
          Activation gain
          <input type="number" step="0.05" min={0} max={1} value={gain} onChange={(event) => setGain(Number(event.target.value))} />
        </label>
      </div>
      <div className="row">
        {Array.from(new Set([...(experiment?.engines || []), ...observedEngines, ...engines])).map((engine) => (
          <label key={engine}>
            <input
              type="checkbox"
              checked={engines.includes(engine)}
              onChange={(event) =>
                setEngines((current) =>
                  event.target.checked ? [...current, engine] : current.filter((item) => item !== engine),
                )
              }
            />
            {engine}
          </label>
        ))}
      </div>
      <button type="button" onClick={() => replay().catch((reason: unknown) => setNote(String(reason)))} disabled={!experiment}>
        Replay with these settings
      </button>
      {note && <p className="error">{note}</p>}
      <h2>Engines</h2>
      <ul>
        {models.map((model) => (
          <li key={model.engine_id}>
            {model.engine_id} · {model.availability} · {model.detail}
          </li>
        ))}
      </ul>
      <h2>Annotation</h2>
      <p className="muted">Annotations stay separate from model observations.</p>
      <div className="controls">
        <label>
          Day
          <input value={day} onChange={(event) => setDay(event.target.value)} />
        </label>
        <label>
          Note
          <input value={annotation} onChange={(event) => setAnnotation(event.target.value)} />
        </label>
        <button
          type="button"
          onClick={() => api.annotate(day, annotation).then(() => setAnnotation(""))}
        >
          Save annotation
        </button>
      </div>
      <p className="muted">{experiments.length} stored experiments.</p>
    </section>
  );
}

function labelFor(id: string, concepts: Concept[]): string {
  const concept = concepts.find((item) => item.id === id);
  if (concept) {
    return concept.name;
  }
  if (id === "mock_conservative") {
    return "Mock conservative";
  }
  if (id === "llm_baseline") {
    return "LLM baseline";
  }
  return id ? id.charAt(0).toUpperCase() + id.slice(1) : id;
}

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#/, "") || "/trajectory";
  const [path] = hash.split("?");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "day") {
    return { name: "day", day: parts[1] || "" };
  }
  if (parts[0] === "taxonomy") {
    return { name: "taxonomy", id: parts[1] };
  }
  if (parts[0] === "evidence" && parts[1]) {
    return { name: "evidence", id: parts[1] };
  }
  if (parts[0] === "settings") {
    return { name: "settings" };
  }
  return { name: "trajectory" };
}
