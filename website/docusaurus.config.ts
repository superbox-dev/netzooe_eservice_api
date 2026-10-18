import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const repository = 'https://github.com/superbox-dev/netzooe_eservice_api';

const config: Config = {
  title: 'Netz OÖ eService API',
  tagline: 'A Python wrapper for the unofficial Netz Oberösterreich eService portal API.',
  favicon: 'img/logo.svg',

  future: {
    v4: true,
  },

  url: 'https://superbox-dev.github.io',
  baseUrl: '/netzooe_eservice_api/',
  trailingSlash: false,

  organizationName: 'superbox-dev',
  projectName: 'netzooe_eservice_api',

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',

  markdown: {
    // The pages are generated from docstrings and the repository Markdown files, so parse them as CommonMark
    format: 'detect',
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        docsRouteBasePath: '/',
        indexBlog: false,
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    docs: {
      sidebar: {
        hideable: true,
      },
    },
    navbar: {
      title: 'Netz OÖ eService API',
      logo: {
        alt: 'superbox logo',
        src: 'img/logo.svg',
      },
      items: [
        {type: 'doc', docId: 'api', label: 'Documentation', position: 'right'},
        {type: 'doc', docId: 'changelog', label: 'Changelog', position: 'right'},
        {href: repository, label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      links: [
        {
          title: 'Documentation',
          items: [
            {label: 'Introduction', to: '/'},
            {label: 'API client', to: '/api'},
            {label: 'Changelog', to: '/changelog'},
          ],
        },
        {
          title: 'Community',
          items: [
            {label: 'Issues', href: `${repository}/issues`},
            {label: 'Discord', href: 'https://discord.com/users/superbox_dev'},
            {label: 'Donation', to: '/donation'},
          ],
        },
        {
          title: 'More',
          items: [
            {label: 'GitHub', href: repository},
            {label: 'PyPI', href: 'https://pypi.org/project/netzooe-eservice-api/'},
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Michael Hacker. Licensed under Apache-2.0.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.oneDark,
      additionalLanguages: ['bash', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
