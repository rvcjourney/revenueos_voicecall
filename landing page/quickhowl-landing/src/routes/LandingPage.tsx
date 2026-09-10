import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Hero } from "@/components/sections/Hero";
import { TrustStrip } from "@/components/sections/TrustStrip";
import { PlatformShowcase } from "@/components/sections/PlatformShowcase";
import { RealCalls } from "@/components/sections/RealCalls";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { PlatformPillars } from "@/components/sections/PlatformPillars";
import { CaseStudies } from "@/components/sections/CaseStudies";
import { WhyVoiceAgents } from "@/components/sections/WhyVoiceAgents";
import { EnterpriseGrade } from "@/components/sections/EnterpriseGrade";
import { About } from "@/components/sections/About";
import { Testimonials } from "@/components/sections/Testimonials";
import { Pricing } from "@/components/sections/Pricing";
import { FAQ } from "@/components/sections/FAQ";
import { Contact } from "@/components/sections/Contact";
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
        <WhyVoiceAgents />
        <EnterpriseGrade />
        <About />
        <Testimonials />
        <Pricing />
        <FAQ />
        <Contact />
        <FinalCTA />
        <Footer />
      </div>
    </PlatformTabProvider>
  );
}
