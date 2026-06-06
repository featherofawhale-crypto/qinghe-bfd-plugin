import { Composition } from "remotion";
import { IntroVideo } from "./IntroVideo";

export const Root: React.FC = () => {
  return (
    <Composition
      id="BFD-Intro"
      component={IntroVideo}
      durationInFrames={1460} // 2:10 at 30fps
      fps={30}
      width={3840}
      height={2160}
    />
  );
};
