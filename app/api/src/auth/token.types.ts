export interface AuthenticatedUser {
  id: string;
  roleId: string;
  permissions: string[];
}
