{{- define "idea-board-backend.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "idea-board-backend.databaseSecretName" -}}
{{- if .Values.postgres.enabled -}}
{{- default (printf "%s-database" .Release.Name) .Values.databaseSecretName -}}
{{- else -}}
{{- required "databaseSecretName must reference an existing database Secret" .Values.databaseSecretName -}}
{{- end -}}
{{- end -}}
