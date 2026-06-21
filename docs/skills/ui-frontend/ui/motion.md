# Motion & Animations

GSAP is the standard for complex programmatic animations. CSS is used for simple micro-interactions. However, **animations must never risk triggering seizures or breaking accessibility norms**.

### Rules & Accessibility Mandates
- **Micro-animations**: Use GSAP `CustomEase` or CSS `cubic-bezier` for a snappy, fluid feel. Ensure Interaction to Next Paint (INP) is always < 200ms.
- **Performance & CLS Prevention**: To maintain a Cumulative Layout Shift (CLS) under < 0.1, always define `width` and `height` on images or use **skeleton loaders** (`shimmer` or `pulse` animations) instead of blank screens while content loads asynchronously. Avoid causing layout jumps.
- **Visibility**: Elements entering the screen should fade/slide in. Ensure all final elements reach a minimum **4.5:1 text-contrast threshold**. Elements starting on-screen must be `100%` visible immediately.
- **Seizure Restrictions (ADA)**: Do not create effects that flash or heavily alternate color more than 3 times per second. Flashing must be tightly controlled or entirely avoided.
- **Reduced Motion**: All animations (CSS or GSAP) must respect `prefers-reduced-motion: reduce`. Users must have the option to easily disable intense visual animation. Disable decorative animations if reduced motion is requested.
- **Hover Lift**: Cards feature a hover lift effect and slight scale-up. On mobile, map these to touch-active states within `44x44px` minimum tap targets.

### GSAP Implementation (React Example)

```jsx
// React + GSAP Stagger Reveal
// Ensure checking prefers-reduced-motion
import { useLayoutEffect, useRef } from 'react';
import gsap from 'gsap';

export function AnimatedList({ items }) {
  const container = useRef(null);
  
  useLayoutEffect(() => {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    if (prefersReducedMotion) {
      gsap.set(container.current.children, { y: 0, opacity: 1 });
      return;
    }

    gsap.fromTo(container.current.children, {
      y: 20, opacity: 0
    }, {
      y: 0, opacity: 1, stagger: 0.05, ease: "power3.out", duration: 0.6
    });
  }, []);

  return <ul ref={container} className="space-y-4" role="list">{/* items */}</ul>;
}
```

### CSS Implementation (UnoCSS/Tailwind)

```html
<!-- Interactive Card with Hover Lift and Accessible Motion -->
<div class="hover:motion-reduce:transform-none transform transition-all duration-300 ease-out hover:-translate-y-1 hover:scale-[1.02] active:scale-[1.0] focus-within:ring-2 focus-within:ring-primary shadow-lg hover:shadow-xl group" tabindex="0">
  Card Content with ADA-compliant Text
</div>
```
