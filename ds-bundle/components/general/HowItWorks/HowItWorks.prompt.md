HowItWorks from @smartervote/design-system. Use via `window.SmarterVoteDS.HowItWorks` (bundle loaded from the root `_ds_bundle.js`).

Three-step numbered explainer section, each step with a top border
accent and a zero-padded mono step number.

## Props

```ts
interface HowItWorksProps {
  eyebrow?: string;
  heading?: React.ReactNode;
  steps?: HowItWorksStep[];
}
```
