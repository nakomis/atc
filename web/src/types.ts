// Mirrors the ATC API contract (api/atc/board.py, api/atc/ordering.py). Ids are Plane UUIDs.

export type PointsSource = 'claude-estimate' | 'martin' | 'mcp';

export interface ItemView {
  id: string;
  ref: string;
  name: string;
  state: string;
  state_group: string;
  priority: string;
  points: number | null;
  points_source: PointsSource | null;
  url: string;
}

export interface ModuleView {
  id: string;
  name: string;
  unsorted: boolean;
  status: string | null;
  points: number;
  unestimated: number;
  items: ItemView[];
}

export interface Card {
  kind: 'project' | 'module';
  id: string;
  project_id: string;
  identifier: string;
  /** Project name for a project card; "IDENT · Module name" for a module card. */
  label: string;
  points: number;
  unestimated: number;
  modules: ModuleView[];
}

export interface Column {
  key: string;
  label: string;
  points: number;
  unestimated: number;
  cards: Card[];
}

export interface Board {
  columns: Column[];
  max_points: number;
  generated_at: string;
}

export interface ProjectMeta {
  id: string;
  identifier: string;
  name: string;
  column: string;
  repo: string | null;
  deploys: boolean;
  deploy_action: string;
  bau_enabled: boolean;
}

export type ProjectPatch = Partial<
  Pick<ProjectMeta, 'repo' | 'deploys' | 'deploy_action' | 'bau_enabled'>
>;

export interface MoveRequest {
  kind: 'project' | 'module';
  id: string;
  to_column: string;
  before_id: string | null;
}

export interface ReorderRequest {
  project_id: string;
  module_id: string;
  before_id: string | null;
}
