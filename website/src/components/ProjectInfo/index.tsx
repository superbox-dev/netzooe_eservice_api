import type {ReactNode} from 'react';
import Link from '@docusaurus/Link';
import {
  mdiBug,
  mdiGithub,
  mdiHistory,
  mdiLanguagePython,
  mdiLightbulbQuestion,
  mdiPackageVariant,
  mdiAccountHeart,
} from '@mdi/js';

import styles from './styles.module.css';

const repository = 'https://github.com/superbox-dev/netzooe_eservice_api';
const maintainer = 'mh-superbox';
// Brand icon of the Home Assistant integration
const brand = 'https://raw.githubusercontent.com/superbox-dev/netzooe_eservice/main/custom_components/netzooe_eservice/brand';

function Icon({path}: {path: string}): ReactNode {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

// Project card above the table of contents, styled after the Home Assistant integration sidebar
export default function ProjectInfo(): ReactNode {
  return (
    <div className={styles.projectInfo}>
      <section className={styles.module}>
        <div className={styles.logo}>
          <div className={styles.brand}>
            <img
              src={`${brand}/icon.png`}
              srcSet={`${brand}/icon@2x.png 2x`}
              alt="Netz OÖ"
              width={128}
              height={128}
            />
          </div>
          <Link href="https://pypi.org/project/netzooe-eservice-api/">
            <img
              src="https://img.shields.io/pypi/v/netzooe-eservice-api?label=PyPI"
              alt="Latest version on PyPI"
              height={20}
            />
          </Link>
        </div>
        <p className={styles.section}>
          An asynchronous Python client for the Netz Oberösterreich eService portal, used by the Home Assistant integration.
        </p>
        <p className={styles.section}>
          A community project, not affiliated with or endorsed by Netz Oberösterreich GmbH. Netz OÖ is a trademark of its owner.
        </p>
        <p className={styles.section}>
          <Icon path={mdiLanguagePython} /> Requires Python 3.13 or newer.
        </p>
        <p className={styles.section}>
          <Link href={repository}>
            <Icon path={mdiGithub} /> View source on GitHub
          </Link>
          <br />
          <Link href={`${repository}/issues?q=is%3Aissue+is%3Aopen+label%3Abug`}>
            <Icon path={mdiBug} /> View known issues
          </Link>
          <br />
          <Link href={`${repository}/issues/new/choose`}>
            <Icon path={mdiLightbulbQuestion} /> Request a feature
          </Link>
          <br />
          <Link href="https://pypi.org/project/netzooe-eservice-api/">
            <Icon path={mdiPackageVariant} /> View on PyPI
          </Link>
          <br />
          <Link to="/changelog">
            <Icon path={mdiHistory} /> Changelog
          </Link>
        </p>
      </section>
      <section className={styles.module}>
        <h2 className={styles.title}>
          <Icon path={mdiAccountHeart} /> Maintainer
        </h2>
        <Link className={styles.owner} href={`https://github.com/${maintainer}`}>
          <img src={`https://avatars.githubusercontent.com/${maintainer}?size=96`} alt="" width={32} height={32} />
          @{maintainer}
        </Link>
      </section>
    </div>
  );
}
