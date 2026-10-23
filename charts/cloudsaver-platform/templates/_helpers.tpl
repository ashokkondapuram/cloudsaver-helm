{{- define "app.fullname" -}}
{{- $name := default .Release.Name .Values.fullnameOverride -}}
{{- if gt (len $name) 40 -}}{{ fail "Use a release name or fullnameOverride of at most 40 characters" }}{{- end -}}
{{- $name -}}
{{- end -}}
{{- define "app.name" -}}
{{- printf "%s-%s" (include "app.fullname" .root) .component -}}
{{- end -}}
{{- define "app.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
{{- define "app.image" -}}
{{- if .digest -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}
{{- define "app.secret" -}}
- name: {{ .env }}
  valueFrom:
    secretKeyRef:
      name: {{ .secret | quote }}
      key: {{ .key | quote }}
{{- end -}}
{{- define "app.security" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}
