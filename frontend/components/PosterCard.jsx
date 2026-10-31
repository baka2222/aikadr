import Link from 'next/link';
import { seriesUrl } from '../lib/api';
import { episodeCount } from '../lib/format';

export default function PosterCard({ series }) {
  return <Link className="poster" href={seriesUrl(series.id)} aria-label={`Открыть сериал ${series.title}`}>
    <div className="cover">
      {series.poster_url ? <img src={series.poster_url} alt="" loading="lazy" /> : <div className="poster-placeholder" />}
      <span className="cover-kicker">{series.author_name || series.genre}</span>
      <span className="cover-name">{series.title}</span>
    </div>
    <div className="poster-meta"><div className="line1"><span>{series.genre}</span><span>{series.year}</span></div><div className="line2">{episodeCount(series.episode_count)} · {series.rating}</div></div>
  </Link>;
}
