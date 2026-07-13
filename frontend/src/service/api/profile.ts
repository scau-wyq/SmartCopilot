import { request } from '../request';

export function fetchProfile() {
  return request<Api.Profile.Detail>({
    url: '/profile',
    method: 'get'
  });
}

export function fetchModelOptions() {
  return request<Api.Model.OptionsResponse>({
    url: '/models/options',
    method: 'get'
  });
}

export function fetchUpdateModelPreference(modelMode: Api.Model.Mode) {
  return request<Api.Profile.ModelSettings>({
    url: '/profile/model-preference',
    method: 'put',
    data: { modelMode }
  });
}

export function fetchSaveCustomLlm(payload: Api.Profile.CustomModelPayload) {
  return request<Api.Profile.ModelSettings>({
    url: '/profile/custom-llm',
    method: 'put',
    data: payload
  });
}

export function fetchTestCustomLlm(payload: Api.Profile.CustomModelPayload) {
  return request<{ success: boolean; message: string }>({
    url: '/profile/custom-llm/test',
    method: 'post',
    data: payload
  });
}
