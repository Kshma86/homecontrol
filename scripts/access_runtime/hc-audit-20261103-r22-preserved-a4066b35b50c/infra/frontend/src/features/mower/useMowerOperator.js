// HC has one superuser; rover credentials remain private to the backend.
export default function useMowerOperator() {
  return { configured: true, authenticated: true, superuser: true, busy: false, error: "", refresh() {}, login() {}, logout() {} };
}
