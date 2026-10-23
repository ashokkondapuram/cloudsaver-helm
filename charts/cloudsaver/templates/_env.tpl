{{- define "app.env" -}}
{{- $root := .root -}}{{- $component := .component -}}
{{- $base := include "app.fullname" $root -}}
{{- if eq $component "web-dashboard" }}
- name: API_GATEWAY_URL
  value: {{ printf "http://%s-api-gateway:8000" $base | quote }}
{{- else }}
{{ include "app.secret" (dict "env" "CLOUDSAVER_DATABASE_URL" "secret" $root.Values.runtimeSecret "key" "database-url") }}
{{ include "app.secret" (dict "env" "REDIS_URL" "secret" $root.Values.runtimeSecret "key" (ternary "redis-gateway-url" "redis-worker-url" (eq $component "api-gateway"))) }}
{{- $callers := dict "api-gateway" "gateway-token" "tenant-service" "tenant-token" "scanner-service" "scanner-token" "analytics-service" "analytics-token" "notification-service" "notification-token" -}}
{{- if hasKey $callers $component }}
{{ include "app.secret" (dict "env" "CLOUDSAVER_IDENTITY_TOKEN" "secret" $root.Values.runtimeSecret "key" (get $callers $component)) }}
{{- end }}
- name: CLOUDSAVER_TRUSTED_CALLERS
  value: {{ ternary "" (printf "%s-api-gateway,%s-analytics-service,%s-notification-service" $base $base $base) (eq $component "api-gateway") | quote }}
{{- if eq $component "api-gateway" }}
- name: CLOUDSAVER_TRUSTED_PROXIES
  value: {{ printf "%s-web-dashboard" $base | quote }}
{{- end }}
{{- end }}
{{- range $name, $ref := (index $root.Values.components $component).secretEnv }}
{{ include "app.secret" (dict "env" $name "secret" $ref.name "key" $ref.key) }}
{{- end }}
{{- end -}}
