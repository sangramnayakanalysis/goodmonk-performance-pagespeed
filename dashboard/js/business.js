/* =====================================================================
   business.js — Plain-English translation module
   ---------------------------------------------------------------------
   PLUGIN ARCHITECTURE CONTRACT
   Pure logic module: no fetch(), no DOM access, no side effects. Takes
   the SAME "top_opportunities" data pages.json already contains
   (produced by the existing, untouched pagespeed.py / dashboard_data.py)
   and maps each Lighthouse diagnostic title to CEO-readable copy.

   Reusable by any tab — Overview today, and the Website Performance
   business-impact enhancement in a later phase — via:
     GMBusiness.explain(topOpportunities) -> [{ title, plain, impact }]
     GMBusiness.statusLabel(statusColor)  -> "Slow" | "Needs attention" | "Healthy" | "No data"
   ===================================================================== */

const GMBusiness = (() => {
  // Keyed by a lowercase substring match against the Lighthouse audit
  // title already present in pages.json's top_opportunities[].title —
  // no backend change needed to add or edit an explanation.
  const DICTIONARY = [
    {
      match: "unused javascript",
      plain: "The page loads scripts it doesn't actually need for what the customer sees first.",
      impact: "Customers wait longer before the page becomes usable.",
    },
    {
      match: "unused css",
      plain: "The page downloads style rules that aren't used on this screen.",
      impact: "Adds delay before content appears, especially on slower connections.",
    },
    {
      match: "render-blocking",
      plain: "Some files must finish loading before the page can start showing anything.",
      impact: "Customers see a blank or frozen screen for longer than necessary.",
    },
    {
      match: "image",
      plain: "Images are larger than they need to be for how they're displayed.",
      impact: "Slower page loads, especially on mobile data connections.",
    },
    {
      match: "server response",
      plain: "The website's server takes noticeable time to start responding.",
      impact: "Every visitor feels a delay before the page even begins loading.",
    },
    {
      match: "text compression",
      plain: "Files are sent uncompressed, making them larger to download than necessary.",
      impact: "Pages load slower than they should, especially outside major cities.",
    },
    {
      match: "next-gen",
      plain: "Images use an older format that takes longer to download than modern alternatives.",
      impact: "Product photos take longer to appear, which can frustrate shoppers.",
    },
    {
      match: "dom size",
      plain: "The page has an unusually large amount of content packed onto it.",
      impact: "The page can feel sluggish to scroll and interact with.",
    },
    {
      match: "third-party",
      plain: "Scripts from outside services (ads, trackers, chat widgets) are slowing the page down.",
      impact: "Customers pay a speed cost for tools that don't directly help them shop.",
    },
    {
      match: "layout shift",
      plain: "Elements on the page move around after they've already loaded.",
      impact: "Customers can accidentally tap the wrong thing — like clicking 'Add to Cart' on the wrong item.",
    },
  ];

  const FALLBACK = {
    plain: "This is a technical loading delay identified by Google's page-speed audit.",
    impact: "Contributes to a slower overall experience for customers.",
  };

  function explain(topOpportunities) {
    if (!Array.isArray(topOpportunities)) return [];
    return topOpportunities.slice(0, 5).map((opp) => {
      const titleLower = (opp.title || "").toLowerCase();
      const found = DICTIONARY.find((d) => titleLower.includes(d.match));
      return {
        title: opp.title || "Loading issue",
        display_value: opp.display_value || "",
        plain: found ? found.plain : FALLBACK.plain,
        impact: found ? found.impact : FALLBACK.impact,
      };
    });
  }

  function explainOne(title) {
    if (!title) return null;
    const titleLower = title.toLowerCase();
    const found = DICTIONARY.find((d) => titleLower.includes(d.match));
    return {
      title,
      plain: found ? found.plain : FALLBACK.plain,
      impact: found ? found.impact : FALLBACK.impact,
    };
  }

  function statusLabel(statusColor) {
    switch (statusColor) {
      case "green": return "Healthy";
      case "yellow": return "Needs Attention";
      case "red": return "Slow";
      default: return "No Data";
    }
  }

  return { explain, explainOne, statusLabel };
})();
