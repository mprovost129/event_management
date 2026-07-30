# Accessibility and Responsive Review

Automated code protections include a skip link, semantic main target, labeled primary navigation, visible keyboard focus, 44-pixel minimum controls, reduced-motion behavior, responsive tables with scoped headers and named keyboard-scroll regions, alternative-text checks, and browser security policies. They do not replace manual review.

Test the platform home, signup/login, subscriber dashboard, content editor, event form, invitation RSVP with guests, ticket checkout handoff, mobile roster/check-in, campaigns, reports, review form, and legal pages.

For each screen record browser, viewport, assistive technology, result, and issue owner:

- [ ] Complete every action with keyboard only; focus order is logical and never trapped.
- [ ] At 200% and 400% zoom, text and controls remain usable without losing content or actions.
- [ ] At 320 CSS pixels wide, no required control is clipped; wide tables have an understandable scroll region.
- [ ] Screen-reader headings, landmarks, labels, errors, status messages, and button purposes are announced meaningfully.
- [ ] Text, controls, focus indicators, and status cues meet WCAG AA contrast; meaning does not depend on color alone.
- [ ] Images have appropriate alternative text or are decorative; uploaded marketing images do not contain essential unrepresented text.
- [ ] Date/time, price, RSVP, payment, consent, and destructive confirmations are unambiguous.
- [ ] Motion respects reduced-motion preference, and no flashing content exists.
- [ ] Test current iOS Safari, Android Chrome, desktop Chrome, Firefox, Edge, and Safari where available.

Public launch is blocked on any issue that prevents signup, RSVP, payment, unsubscribe, check-in, or policy access for keyboard or screen-reader users.
