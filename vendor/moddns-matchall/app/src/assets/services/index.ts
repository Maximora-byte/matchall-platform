type LogoVariants = {
    base?: string;
    dark_mode?: string;
    light_mode?: string;
};

// TODO: Consider lazy-loading service logos when code splitting is complete
function buildServiceLogoMap(): Record<string, LogoVariants> {
    const svgModules = import.meta.glob("./*.svg", { eager: true, import: "default" }) as Record<
        string,
        string
    >;
    const pngModules = import.meta.glob("./*.png", { eager: true, import: "default" }) as Record<
        string,
        string
    >;

    const allModules: Record<string, string> = { ...svgModules, ...pngModules };
    const map: Record<string, LogoVariants> = {};

    for (const [path, src] of Object.entries(allModules)) {
        const file = path.split("/").pop();
        if (!file) continue;

        const baseName = file.replace(/\.(svg|png)$/i, "");

        let variant: keyof LogoVariants = "base";
        let servicePart = baseName;

        if (baseName.endsWith("_dark_mode")) {
            variant = "dark_mode";
            servicePart = baseName.slice(0, -"_dark_mode".length);
        } else if (baseName.endsWith("_light_mode")) {
            variant = "light_mode";
            servicePart = baseName.slice(0, -"_light_mode".length);
        }

        const key = normalizeServiceKey(servicePart);
        if (!key) continue;

        map[key] ??= {};
        map[key][variant] = src;
    }

    return map;
}

const SERVICE_LOGOS: Record<string, LogoVariants> = buildServiceLogoMap();

function normalizeServiceKey(value: string): string {
    return value.trim().toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function getServiceLogoSrc(params: {
    serviceId?: string | null;
    serviceName?: string | null;
    isDark?: boolean;
}): string | undefined {
    const raw = params.serviceId || params.serviceName;
    if (!raw) return undefined;

    const key = normalizeServiceKey(raw);
    const variants = SERVICE_LOGOS[key];
    if (!variants) return undefined;

    if (params.isDark) return variants.dark_mode ?? variants.base ?? variants.light_mode;
    return variants.light_mode ?? variants.base ?? variants.dark_mode;
}
