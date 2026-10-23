{{- define "app.env" -}}
{{- $root := .root -}}{{- $component := .component -}}
{{- if eq $component "identity-service" }}
{{ include "app.secret" (dict "env" "PLATFORM_IDENTITY_DATABASE_URL" "secret" $root.Values.identitySecret "key" "database-url") }}
{{ include "app.secret" (dict "env" "PLATFORM_REDIS_URL" "secret" $root.Values.identitySecret "key" "redis-url") }}
{{ include "app.secret" (dict "env" "PLATFORM_IDENTITY_CALLERS" "secret" $root.Values.identitySecret "key" "caller-digests") }}
{{ include "app.secret" (dict "env" "PLATFORM_KEY_PEPPER" "secret" $root.Values.identitySecret "key" "key-pepper") }}
{{- else }}
- name: IDENTITY_SERVICE_URL
  value: {{ printf "http://%s-identity-service:8005" (include "app.fullname" $root) | quote }}
- name: PLATFORM_ENVIRONMENT
  value: production
- name: PLATFORM_PORTAL_AUTH
  value: entra
- name: PORTAL_PUBLIC_URL
  value: {{ $root.Values.publicUrl | quote }}
- name: PORTAL_ENTRA_TENANT_ID
  value: {{ $root.Values.entra.tenantId | quote }}
- name: PORTAL_ENTRA_CLIENT_ID
  value: {{ $root.Values.entra.clientId | quote }}
- name: PORTAL_ENTRA_API_SCOPE
  value: {{ $root.Values.entra.apiScope | quote }}
{{ include "app.secret" (dict "env" "PLATFORM_PORTAL_TOKEN" "secret" $root.Values.portalSecret "key" "caller-token") }}
{{ include "app.secret" (dict "env" "PORTAL_ENTRA_CLIENT_SECRET" "secret" $root.Values.portalSecret "key" "entra-client-secret") }}
{{- end }}
{{- range $name, $ref := (index $root.Values.components $component).secretEnv }}
{{ include "app.secret" (dict "env" $name "secret" $ref.name "key" $ref.key) }}
{{- end }}
{{- end -}}
