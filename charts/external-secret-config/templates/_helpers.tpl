{{- define "external-secret-config.name" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.fullnameOverride -}}
{{- end -}}
