// The 28 states electing a governor on 6 February 2027. The other eight (Anambra, Bayelsa, Edo, Ekiti, Imo, Kogi,
// Ondo, Osun) vote off-cycle after court rulings moved their terms.
export const GOV_STATES = [
  "Abia", "Adamawa", "Akwa Ibom", "Bauchi", "Benue", "Borno", "Cross River", "Delta", "Ebonyi", "Enugu", "Gombe", "Jigawa",
  "Kaduna", "Kano", "Katsina", "Kebbi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Oyo", "Plateau", "Rivers",
  "Sokoto", "Taraba", "Yobe", "Zamfara",
] as const;
export const govSlug = (s: string) => s.toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");
