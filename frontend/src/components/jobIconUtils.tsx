import { PythonIcon, ReactIcon, CodeIcon, CloudIcon, DatabaseIcon } from './TechIcons';

export const getJobTechIcon = (title: string) => {
  const t = title.toLowerCase();
  if (t.includes('python')) return <PythonIcon />;
  if (t.includes('react') || t.includes('frontend')) return <ReactIcon />;
  if (t.includes('devops') || t.includes('infrastructure') || t.includes('cloud')) return <CloudIcon />;
  if (t.includes('data') || t.includes('database') || t.includes('sql')) return <DatabaseIcon />;
  return <CodeIcon />;
};

