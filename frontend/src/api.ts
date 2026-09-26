export interface Experiment {
  id: string;
  name: string;
  engines: string[];
  decay_type: string;
  half_life_hours: number;
  reservoir_update: string;
  activation_gain: number;
  core_scoring_mode: string;
  notes: string;
}

export interface Concept {
  id: string;
  name: string;
  family: string;
  status: string;
  locked: boolean;
  first_seen: string | null;
  support_count: number;
  version: number | null;
  definition: string;
}

export interface SeriesPoint {
  t: string;
  level: number | null;
  observed?: boolean;
  observation_count?: number;
  observation_id?: string;
  episode_id?: string;
  concentration?: number | null;
  concept_version?: number;
  question_version?: number;
  evidence_episodes?: number;
  user_word_count?: number;
  native_output_type?: string;
}

export interface SeriesLine {
  engine_id?: string;
  concept_id?: string;
  points: SeriesPoint[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${response.status} ${path}`);
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${path}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  experiments: () => get<{ experiments: Experiment[] }>("/api/experiments"),
  status: () => get<{ observations: Record<string, number> }>("/api/status"),
  concepts: (status?: string) => get<{ concepts: Concept[] }>(`/api/taxonomy${status ? `?status=${status}` : ""}`),
  concept: (id: string) => get<Record<string, unknown>>(`/api/taxonomy/${encodeURIComponent(id)}`),
  models: () =>
    get<{ engines: { engine_id: string; display_name: string; availability: string; kind: string; detail: string }[] }>(
      "/api/models",
    ),
  series: (experimentId: string, conceptId: string, mode: string) =>
    get<{ series: SeriesLine[]; experiment: Experiment }>(
      `/api/series?experiment_id=${experimentId}&concept_id=${encodeURIComponent(conceptId)}&mode=${mode}`,
    ),
  compare: (experimentId: string, engineId: string, conceptIds: string[], mode: string) =>
    get<{ series: SeriesLine[]; experiment: Experiment }>(
      `/api/compare?experiment_id=${experimentId}&engine_id=${engineId}&concept_ids=${conceptIds.map(encodeURIComponent).join(",")}&mode=${mode}`,
    ),
  day: (day: string, experimentId: string, engineId: string) =>
    get<Record<string, unknown>>(`/api/days/${day}?experiment_id=${experimentId}&engine_id=${engineId}`),
  observation: (id: string, experimentId: string) =>
    get<Record<string, unknown>>(`/api/observations/${id}?experiment_id=${experimentId}`),
  createExperiment: (body: Record<string, unknown>) => post<{ id: string }>("/api/experiments", body),
  replay: (id: string) => post<Record<string, unknown>>(`/api/experiments/${id}/replay`, {}),
  annotate: (day: string, text: string) => post<{ id: string }>("/api/annotations", { day, text }),
  rate: (day: string, conceptId: string, rating: number, note: string) =>
    post<{ id: string }>("/api/self-ratings", { day, concept_id: conceptId, rating, note }),
  setStatus: (id: string, status: string, day: string, rationale: string) =>
    post(`/api/taxonomy/${encodeURIComponent(id)}/status`, { status, day, rationale }),
};
