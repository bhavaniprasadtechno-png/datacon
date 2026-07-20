# Custom Reusable Alert Dialog and Programmatic Confirmation Spec

Replace the browser's default `window.confirm` dialog in the sidebar with a reusable, custom styled Radix UI `@radix-ui/react-alert-dialog` component that matches the application theme.

## Goal

To improve user experience and visual consistency by replacing standard browser alert confirmations with a custom, accessible, and theme-matching React Alert Dialog using `@radix-ui/react-alert-dialog`.

## Proposed Changes

### Component Design

#### 1. [NEW] `src/components/ui/AlertDialog.tsx`
Scaffold the `@radix-ui/react-alert-dialog` primitives, styled with CSS properties to match the app theme:
- Custom styles for backdrop blur overlay.
- Content box matching the existing modal (padding, border radius, box shadow).
- Proper exports for title, description, footer, action (confirm), and cancel.

#### 2. [MODIFY] `src/components/ui/ConfirmHost.tsx`
Refactor the global confirmation modal shell:
- Swap out the custom home-grown `Modal` component in favor of the new `AlertDialog`.
- Render the title, description, cancel, and delete/action buttons using the reusable components.

#### 3. [MODIFY] `src/components/shell/Sidebar.tsx`
Integrate the programmatic confirmation hook:
- Import `useConfirm` from `../../stores/useConfirmStore`.
- Call `const confirm = useConfirm()` in `Sidebar`.
- Replace `window.confirm` in `removeConversation` with the promise-based `confirm({...})` call.

## Verification Plan

### Automated Tests
- Run `npm run build` in `app/web` to verify zero TypeScript or bundle compilation errors.

### Manual Verification
- Trigger conversation deletion from the Sidebar to verify the custom confirmation modal appears.
- Verify Cancel and Confirm buttons behave correctly (closing the modal vs. deleting the conversation).
