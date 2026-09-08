const configuredAssetBaseUrl = import.meta.env.VITE_ASSET_BASE_URL || ''
const assetBaseUrl = (configuredAssetBaseUrl || import.meta.env.BASE_URL).replace(/\/$/, '')

export const whaleGirlLogoUrl = `${assetBaseUrl}/assets/asu-agent.svg`
export const whaleGirlHeroUrl = `${assetBaseUrl}/assets/asu-agent.svg`
