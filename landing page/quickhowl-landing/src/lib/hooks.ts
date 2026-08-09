import { useQuery } from "@tanstack/react-query";
import { plansApi } from "@/lib/api";

export function usePublicPlans() {
  return useQuery({ queryKey: ["public-plans"], queryFn: () => plansApi.list().then((r) => r.data) });
}
