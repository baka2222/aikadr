import './globals.css';
import './overrides.css';
import './member.css';
import './premium.css';
import Header from '../components/Header';
import SiteProvider from '../components/SiteProvider';
import Footer from '../components/Footer';

export const metadata = {
  title: 'aikadr — истории нового времени',
  description: 'Авторские ИИ-сериалы и видео. Открывайте новые истории и смотрите любимые серии на aikadr.',
  icons: { icon: '/brand/aikadr-square.png', apple: '/brand/aikadr-square.png' },
};

export default function RootLayout({ children }) {
  return (
    <html lang="ru">
      <body>
        <a className="skip-link" href="#main">Перейти к содержимому</a>
        <SiteProvider>
          <Header />
          <main id="main">{children}</main>
          <Footer />
        </SiteProvider>
      </body>
    </html>
  );
}
