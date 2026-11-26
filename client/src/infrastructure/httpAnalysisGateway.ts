import type { AnalysisGateway } from '../application/ports';
import type { Recommendation } from '../domain/analysis';
import { requestJson } from './requestJson';

interface AnalyzeResponse {
  recommendations: Recommendation[];
  model_error: string | null;
}

interface AdaptedResponse {
  injected_css: string;
  applied: string[];
  skipped: string[];
}

const postJson = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

/** Talks to the analysis backend through the capture server's /backend forwarding (see backendProxy.js). */
export function createHttpAnalysisGateway(): AnalysisGateway {
  return {
    analyze: async (html) => {
      // rules_only: the model's text suggestions come from the general metrics, so they are asked for below.
      const response = await requestJson<AnalyzeResponse>(
        '/backend/analyze',
        postJson({ html, rules_only: true }),
      );
      return { recommendations: response.recommendations, modelError: response.model_error };
    },
    analyzeGeneral: async (html, url) => {
      const response = await requestJson<AnalyzeResponse & { layout_error: string | null }>(
        '/backend/analyze_general',
        postJson({ html, url, render: true }),
      );
      return {
        recommendations: response.recommendations,
        modelError: response.model_error,
        layoutError: response.layout_error,
      };
    },
    adapt: async (html, recommendations) => {
      const response = await requestJson<AdaptedResponse>(
        '/backend/adapted',
        postJson({ html, recommendations }),
      );
      return { injectedCss: response.injected_css, applied: response.applied, skipped: response.skipped };
    },
  };
}
