import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Temporary fix for DeckGL maxTextureDimension2D context error
  reactStrictMode: false,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "api.gbif.org" },
      { protocol: "https", hostname: "inaturalist-open-data.s3.amazonaws.com" },
      { protocol: "https", hostname: "*.supabase.co" },
    ],
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      "maplibre-gl": "maplibre-gl",
    };
    return config;
  },
  turbopack: {
    resolveAlias: {
      "maplibre-gl": "maplibre-gl",
    },
  },
};

export default nextConfig;
