export interface PublicPlan {
  id: string;
  name: string;
  price_minor: number;
  discount_price_minor: number | null;
  currency: string;
  credits_per_month: number;
  is_custom_pricing: boolean;
  is_highlighted: boolean;
  marketing_bullets: string[];
}
