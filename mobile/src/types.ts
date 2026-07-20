export type User = {
  id: number; email: string; role: string; staff_id: number | null;
  name: string; phone: string; photo: string; place: string;
};

export type Project = {
  id: number; project_no: string; name: string; client_name: string; place: string;
  status: string; start_date: string; handout_date: string; duration: string;
  area: string; type: string; value: string; description: string;
  latest_progress: string; latest_progress_status: string;
};

export type Dashboard = {
  user: User;
  metrics: Record<string, number>;
  recent_projects: Project[];
};

export type Enquiry = {
  id: number; title: string; client_name: string; client_email: string;
  client_phone: string; status: string; assigned_to: string | null;
  created_at: string; updated_at: string; description?: string;
  comments?: {id: number; author: string; comment: string; created_at: string}[];
  quotations?: {id: number; version: number; amount: string; status: string; details: string}[];
  attachments?: {id: number; name: string; url: string; is_cad: boolean}[];
  available_actions?: string[];
  estimators?: {id: number; name: string}[];
};

export type RootStackParamList = {
  Main: undefined;
  ProjectDetail: {projectId: number; title: string};
  Chat: {projectId: number; title: string};
  SiteUpdate: {projectId: number; works: {id: number; name: string}[]};
  EnquiryDetail: {enquiryId: number; title: string};
};

export type TabParamList = {
  Home: undefined; Projects: undefined; Workflow: undefined;
  Alerts: undefined; Profile: undefined;
};
