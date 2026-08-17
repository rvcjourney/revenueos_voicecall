import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Hero } from "@/components/sections/Hero";
import { TrustStrip } from "@/components/sections/TrustStrip";
import { PlatformShowcase } from "@/components/sections/PlatformShowcase";
import { RealCalls } from "@/components/sections/RealCalls";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { PlatformPillars } from "@/components/sections/PlatformPillars";
import { CaseStudies } from "@/components/sections/CaseStudies";
import { EnterpriseGrade } from "@/components/sections/EnterpriseGrade";
import { Testimonials } from "@/components/sections/Testimonials";
import { Pricing } from "@/components/sections/Pricing";
import { FAQ } from "@/components/sections/FAQ";
import { FinalCTA } from "@/components/sections/FinalCTA";
import { PlatformTabProvider } from "@/lib/platformTab";
import { useScrollReveal } from "@/lib/hooks";

export default function LandingPage() {
  useScrollReveal();

  return (
    <PlatformTabProvider>
      <div className="min-h-screen overflow-x-clip bg-background">
        <Nav />
        <Hero />
        <TrustStrip />
        <PlatformShowcase />
        <RealCalls />
        <HowItWorks />
        <PlatformPillars />
        <CaseStudies />
        <EnterpriseGrade />
        <Testimonials />
        <Pricing />
        <FAQ />
        <FinalCTA />
        <Footer />
      </div>
    </PlatformTabProvider>
  );
}
