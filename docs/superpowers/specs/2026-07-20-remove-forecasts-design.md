# Disable Forecasts Page Spec

Disable the Forecasts page and navigation by commenting them out in the frontend client, preserving the underlying page and API files for future use.

## Goal

To temporarily remove the Forecasts page from the user interface and navigation menu, while leaving the page component and API query code intact (but commented out where imported or registered).

## Proposed Changes

### 1. [MODIFY] `app/web/src/components/shell/Sidebar.tsx`
- Comment out the `forecasts` navigation item in the `NAV` array so that it no longer appears in the sidebar menu.

### 2. [MODIFY] `app/web/src/App.tsx`
- Comment out the import statement for `ForecastsPage`.
- Comment out the `/forecasts` route in the `AppRoutes` definition.

## Verification Plan

### Automated Tests
- Run `npm run build` in `app/web` to verify that commenting out the routes does not cause any TypeScript or packaging errors.

### Manual Verification
- Access the application in the browser and verify that "Forecasts" no longer appears in the sidebar menu.
- Attempt to navigate to `/forecasts` directly and verify that it redirects or falls back (due to the commented route).
