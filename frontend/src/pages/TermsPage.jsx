import { Link } from 'react-router-dom'

/**
 * Draft Terms of Service.
 *
 * Every statement below describes behaviour that exists in this repository
 * (see README sections 1, 10, 14 and 15). Items that depend on who operates a
 * given deployment are marked as drafts instead of being invented.
 */
export default function TermsPage() {
  return (
    <>
      <header className="page-head">
        <div>
          <h1 className="page-title">Terms of Service</h1>
          <p className="page-subtitle">
            Draft for legal review. It describes how this software behaves today, not a
            commitment made on behalf of any operator.
          </p>
        </div>
      </header>

      <article className="panel prose">
        <p className="small faint">
          Last updated: not set. Add a date when these terms are approved.
        </p>

        <h2>1. What HawkEYE is</h2>
        <p>
          HawkEYE, also called the Social Media Data Parser and Intelligence System, is
          software for parsing social media datasets, training machine learning models on
          them, and producing evidence packages with a verifiable chain of custody. You run
          it on infrastructure you control. There is no hosted service.
        </p>

        <h2>2. Model outputs are estimates, not findings</h2>
        <p>
          The automated account score, the misinformation label, the sentiment label and the
          topic assignments are statistical outputs. They are not determinations about any
          real person, organisation or claim. The models shipped with this repository are
          trained on synthetic data and are demonstration grade.
        </p>
        <p>
          Do not use these outputs on their own to accuse, suspend, de-platform or profile
          anyone. The network graph shows interactions found in the dataset you loaded. It
          does not establish coordination.
        </p>

        <h2>3. Data you supply</h2>
        <ul>
          <li>
            You are responsible for confirming that any dataset you upload or collect may be
            used for your purpose, including its licence and the terms of its source.
          </li>
          <li>
            Keep personal data out of uploads. IP addresses are redacted automatically at
            ingestion. Other personal information inside free text is your responsibility.
          </li>
          <li>
            Record provenance for datasets you add, in
            <code> backend/datasets/dataset_catalog.json</code>.
          </li>
        </ul>

        <h2>4. Collection from the web</h2>
        <p>
          Outbound collection reaches only sources that publish unauthenticated read access
          or that permit automated access. The software never signs in, never stores
          credentials and never works around access controls. It honours{' '}
          <code>robots.txt</code> unless an operator disables that setting, applies a delay
          between requests to the same host, and refuses requests to private network
          addresses, re-checking after every redirect.
        </p>
        <p>
          Platforms that prohibit automated access, currently X, Reddit, LinkedIn, Facebook,
          Instagram and Threads, fail immediately with an explanation. Do not attempt to
          bypass these controls. Setting <code>SMDPIS_FETCH_ENABLED=false</code> disables all
          outbound traffic while uploads keep working.
        </p>

        <h2>5. Security is the operator's responsibility</h2>
        <p>
          This release contains no authentication or authorisation layer. Anyone who can
          reach the API can read and modify every dataset, model and evidence item. Deploy it
          behind a reverse proxy that enforces access control, and set a strong{' '}
          <code>SMDPIS_SECRET_KEY</code>, which signs the audit trail. A deployment left open
          to a network is a deployment with no chain of custody worth presenting.
        </p>

        <h2>6. Evidence and audit records</h2>
        <p>
          Ingested files are written once and hashed with SHA-256. Each later action appends
          an audit event signed with HMAC-SHA256. The verification endpoint re-hashes the
          stored file and re-checks every signature. Deleting a dataset changes its status and
          keeps its custody trail, so records are not destroyed by routine dataset management.
        </p>
        <p>
          Verification confirms that the stored bytes and the audit chain are intact. It does
          not prove anything about how the source data was produced before you received it.
        </p>

        <h2>7. No warranty</h2>
        <p>
          The software is provided as is, without warranty of any kind. The authors are not
          liable for decisions made using its outputs. Accuracy figures shown in the interface
          come from held-out evaluation of whichever model is active, and apply only to the
          dataset that model was trained on.
        </p>

        <h2>8. Licence</h2>
        <p>
          <span className="draft-flag">Draft</span>
          Name the repository licence here and link to the licence file. The bundled synthetic
          sample dataset is released under the same terms as the code.
        </p>

        <h2>9. Governing law and contact</h2>
        <p>
          <span className="draft-flag">Draft</span>
          Add the operating entity, its jurisdiction, the governing law, and a contact address
          for legal notices. These depend on who deploys HawkEYE and cannot be filled in by
          the software.
        </p>

        <h2>10. Changes</h2>
        <p>
          <span className="draft-flag">Draft</span>
          State how users will be told about changes to these terms, and whether continued use
          counts as acceptance.
        </p>

        <p className="mt-24">
          See also the <Link to="/privacy">Privacy Policy</Link>.
        </p>
      </article>
    </>
  )
}
