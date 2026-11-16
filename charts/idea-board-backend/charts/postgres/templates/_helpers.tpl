{{- define "idea-board-postgres.name" -}}
{{- default (printf "%s-postgres" .Release.Name | trunc 63 | trimSuffix "-") .Values.fullnameOverride -}}
{{- end -}}
