export interface AuthenticatedUser {
  id: string;
  orgId: string;
  roleId: string;
  permissions: string[];
}
