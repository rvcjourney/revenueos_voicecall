import axios from "axios";
import { API_BASE_URL } from "@/lib/env";
import type { PublicPlan } from "@/lib/types";

export const api = axios.create({ baseURL: API_BASE_URL, timeout: 20000 });

export const plansApi = {
  list: () => api.get<PublicPlan[]>("/api/plans"),
};
